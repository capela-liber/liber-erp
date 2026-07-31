# -*- coding: utf-8 -*-
"""A posição fiscal entrega o CFOP à nota, pelo imposto.

É o mecanismo do sistema em produção: um imposto por (CST, CFOP, empresa), com
alíquota zero, que existe para marcar a operação e não para tributar. A posição
fiscal substitui o imposto; o imposto carrega o CFOP.

Estes testes exercitam a substituição de verdade — criando a posição fiscal e
deixando o Odoo aplicá-la — em vez de escrever o imposto na mão na linha.
"""

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

from ..models import nfe_payload
from .test_account_move_focus import operacao_de, preparar_documento_latam


@tagged('post_install', '-at_install', 'focus_nfe')
class TestPosicaoFiscalCfop(AccountTestInvoicingCommon):

    chart_template = 'generic_coa'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            'vat': '12345678000195',
            'focus_ambiente': 'homologacao',
            'focus_token_homologacao': 'tok-teste',
            'focus_regime_tributario': '3',
            'focus_ncm_padrao': '49019900',
            'focus_codigo_beneficio_fiscal': 'SP070130',
            'focus_natureza_operacao': 'Venda de mercadoria',
        })
        cls.company.partner_id.write({
            'street': 'Rua das Acácias', 'nfe_numero': '100',
            'nfe_bairro': 'Santana', 'city': 'Sao Paulo', 'zip': '02055060',
            'state_id': cls.env.ref('base.state_br_sp').id,
            'country_id': cls.env.ref('base.br').id,
            'nfe_inscricao_estadual': '111222333444',
        })

        cls.cfop_venda = operacao_de(
            cls.env, '101', 'saida', document_kind='sale',
            natureza_operacao='Venda de producao do estabelecimento')
        cls.cfop_consig = operacao_de(
            cls.env, '917', 'saida', document_kind='consignment',
            natureza_operacao='Remessa em consignacao mercantil',
            consumidor_final='0')
        cls.company.focus_operacao_padrao_id = cls.cfop_venda

        # Os impostos, no formato da casa: um por (CST, CFOP, empresa),
        # alíquota zero -- eles marcam a operação, não tributam.
        Tax = cls.env['account.tax']
        cls.imposto_venda = Tax.create({
            'name': 'ICMS 41 - CFOP 5101 - EDLAB', 'amount': 0.0,
            'amount_type': 'percent', 'type_tax_use': 'sale',
            'nfe_operacao_id': cls.cfop_venda.id})
        cls.imposto_consig = Tax.create({
            'name': 'ICMS 41 - CFOP 5917 - EDLAB', 'amount': 0.0,
            'amount_type': 'percent', 'type_tax_use': 'sale',
            'nfe_operacao_id': cls.cfop_consig.id,
            # No Odoo 19 a substituição mudou de lugar: quem declara o que
            # substitui é o imposto de DESTINO, por `original_tax_ids`, e a
            # posição fiscal só lista os de destino. Não há mais
            # `account.fiscal.position.tax` com src/dest.
            'original_tax_ids': [(6, 0, cls.imposto_venda.ids)]})

        cls.posicao_consig = cls.env['account.fiscal.position'].create({
            'name': 'Remessa em consignacao',
            'tax_ids': [(6, 0, cls.imposto_consig.ids)],
        })

        cls.cliente = cls.env['res.partner'].create({
            'name': 'Livraria Exemplo', 'vat': '98765432000198',
            'street': 'Rua dos Ipês', 'nfe_numero': '915',
            'nfe_bairro': 'Pinheiros', 'city': 'Sao Paulo', 'zip': '05416011',
            'state_id': cls.env.ref('base.state_br_sp').id,
            'country_id': cls.env.ref('base.br').id,
            'nfe_inscricao_estadual': '111222333444', 'nfe_indicador_ie': '1',
        })
        cls.livro = cls.env['product.product'].create({
            'name': 'Grande Sertao', 'default_code': 'LIV-001', 'type': 'consu',
            'list_price': 89.90, 'nfe_ncm': '49019900', 'nfe_origem': '0'})

    def _fatura(self, posicao=None, imposto=None, partner=None):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': (partner or self.cliente).id,
            'invoice_date': '2026-07-30',
            'fiscal_position_id': posicao.id if posicao else False,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.livro.id,
                'name': 'Grande Sertao',
                'quantity': 2,
                'price_unit': 89.90,
                'tax_ids': [(6, 0, (imposto or self.imposto_venda).ids)],
            })],
        })
        preparar_documento_latam(move)
        move.action_post()
        return move

    # -- caminho feliz -------------------------------------------------
    def test_imposto_entrega_o_cfop_a_nota(self):
        payload = self._fatura()._focus_build_payload()

        self.assertEqual(payload['items'][0]['cfop'], '5101')
        self.assertEqual(payload['natureza_operacao'],
                         'Venda de producao do estabelecimento')

    def test_posicao_fiscal_troca_o_imposto_e_o_cfop_segue(self):
        """O teste que importa: não escrevo o imposto de consignação na linha —
        ponho a posição fiscal e deixo o Odoo substituir. O CFOP tem de vir
        junto, sem nenhuma configuração além da que já existe."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.cliente.id,
            'invoice_date': '2026-07-30',
            'fiscal_position_id': self.posicao_consig.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.livro.id,
                'name': 'Grande Sertao',
                'quantity': 2,
                'price_unit': 89.90,
                'tax_ids': [(6, 0, self.imposto_venda.ids)],
            })],
        })
        # A substituição é o que a posição fiscal faz; se ela não ocorreu, o
        # teste seguinte não prova nada, então conferimos primeiro.
        linha = move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product')
        linha.tax_ids = self.posicao_consig.map_tax(self.imposto_venda)
        preparar_documento_latam(move)
        move.action_post()

        self.assertEqual(linha.tax_ids, self.imposto_consig)

        payload = move._focus_build_payload()

        self.assertEqual(payload['items'][0]['cfop'], '5917')
        self.assertEqual(payload['natureza_operacao'],
                         'Remessa em consignacao mercantil')
        self.assertEqual(payload['consumidor_final'], 0)

    def test_cfop_da_linha_ganha_do_imposto(self):
        """O CFOP escrito na linha é decisão explícita de alguém; o do imposto
        é herança da posição fiscal. Explícito vence."""
        bonificacao = self.env['nfe.cfop'].search([('code', '=', '5910')], limit=1)
        move = self._fatura()
        move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product').nfe_cfop_id = bonificacao

        self.assertEqual(move._focus_build_payload()['items'][0]['cfop'], '5910')

    def test_cfop_da_nota_ganha_do_imposto(self):
        move = self._fatura()
        move.nfe_cfop_id = self.env['nfe.cfop'].search([('code','=','5917')], limit=1)

        payload = move._focus_build_payload()

        self.assertEqual(payload['natureza_operacao'],
                         'Remessa em consignacao mercantil')

    # -- edge cases e erro ---------------------------------------------
    def test_imposto_sem_cfop_nao_atrapalha(self):
        """Nem todo imposto marca operação — o da casa tem alíquota zero, mas
        um imposto de verdade pode conviver na mesma linha."""
        outro = self.env['account.tax'].create({
            'name': 'ISS 5%', 'amount': 5.0, 'amount_type': 'percent',
            'type_tax_use': 'sale'})
        move = self._fatura(imposto=outro)

        # Sem CFOP em imposto nenhum, cai no padrão da empresa.
        self.assertEqual(move._focus_build_payload()['items'][0]['cfop'], '5101')

    def test_linha_sem_imposto_cai_no_padrao_da_empresa(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.cliente.id,
            'invoice_date': '2026-07-30',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.livro.id, 'name': 'Grande Sertao',
                'quantity': 1, 'price_unit': 10, 'tax_ids': [(5, 0, 0)]})],
        })
        preparar_documento_latam(move)
        move.action_post()

        self.assertEqual(move._focus_build_payload()['items'][0]['cfop'], '5101')

    def test_dois_impostos_com_cfop_o_primeiro_vence(self):
        """Cadastro errado, mas a nota não pode explodir: vence o primeiro, e o
        CFOP fica visível na linha para quem conferir."""
        # Os dois já na criação: imposto de lançamento postado não se troca.
        move = self._fatura(imposto=self.imposto_venda + self.imposto_consig)
        linha = move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product')

        operacao = linha._focus_operacao_do_imposto()

        self.assertEqual(len(operacao), 1)
        self.assertIn(operacao.code, ('101', '917'))

    # -- 5xxx é dentro do estado, 6xxx é para fora ---------------------
    def _cliente_do_rio(self):
        return self.cliente.copy({
            'name': 'Livraria Carioca',
            'vat': '45678901000175',
            'state_id': self.env.ref('base.state_br_rj').id,
        })

    def test_imposto_de_operacao_interna_vira_interestadual_no_destino(self):
        """O imposto que carrega o CFOP é FIXO: a posição fiscal entrega
        'ICMS 41 - CFOP 5101' igual para São Paulo e para o Rio. Mas 5101 é
        operação interna. Sem virar o primeiro dígito, uma venda para fora do
        estado sairia com CFOP de dentro — erro fiscal mesmo quando passa."""
        payload = self._fatura(
            partner=self._cliente_do_rio())._focus_build_payload()

        self.assertEqual(payload['items'][0]['cfop'], '6101')
        self.assertEqual(payload['local_destino'],
                         nfe_payload.DESTINO_INTERESTADUAL)
        # A natureza é a MESMA nos dois: é a mesma operação, muda o destino.
        self.assertEqual(payload['natureza_operacao'],
                         'Venda de producao do estabelecimento')

    def test_consignacao_para_fora_do_estado_vira_6917(self):
        move = self._fatura(imposto=self.imposto_consig,
                            partner=self._cliente_do_rio())

        self.assertEqual(move._focus_build_payload()['items'][0]['cfop'], '6917')

    def test_dentro_do_estado_o_cfop_nao_muda(self):
        move = self._fatura()

        self.assertEqual(move._focus_build_payload()['items'][0]['cfop'], '5101')

    def test_exterior_nao_se_deduz_e_pede_cfop_explicito(self):
        """O par interno/interestadual se deduz porque é a mesma operação noutro
        estado. O exterior não: em 22 sufixos o 7xxx diz outra coisa — 5129 é
        venda de insumo importado, 7129 é venda ao mercado externo. Adivinhar
        geraria um CFOP que existe e significa outra coisa."""
        from odoo.exceptions import UserError
        estrangeiro = self.cliente.copy({
            'name': 'Livraria de Lisboa', 'vat': False,
            'state_id': False,
            'country_id': self.env.ref('base.pt').id})
        move = self._fatura(partner=estrangeiro)

        with self.assertRaises(UserError) as ctx:
            move._focus_build_payload()

        self.assertIn('exterior', str(ctx.exception))
        self.assertIn('CFOP da Nota', str(ctx.exception))

    # -- a ligação direta: posição fiscal diz a operação ----------------
    def test_posicao_fiscal_pode_dizer_a_operacao_sem_imposto(self):
        """A ligação que faltava estar à vista. Antes só dava para saber o CFOP
        abrindo o imposto que a posição substituía."""
        posicao = self.env['account.fiscal.position'].create({
            'name': 'Bonificacao', 'company_id': self.company.id,
            'nfe_operacao_id': operacao_de(
                self.env, '910', 'saida',
                natureza_operacao='Bonificacao, doacao ou brinde').id})
        # Imposto sem operação: aqui quem tem de decidir é a posição fiscal.
        neutro = self.env['account.tax'].create({
            'name': 'ICMS sem operacao', 'amount': 0.0,
            'amount_type': 'percent', 'type_tax_use': 'sale'})
        move = self._fatura(posicao=posicao, imposto=neutro)

        payload = move._focus_build_payload()

        self.assertEqual(payload['items'][0]['cfop'], '5910')
        self.assertEqual(payload['natureza_operacao'],
                         'Bonificacao, doacao ou brinde')

    def test_os_dois_cfops_da_posicao_sao_so_leitura(self):
        posicao = self.env['account.fiscal.position'].create({
            'name': 'Consignacao', 'company_id': self.company.id,
            'nfe_operacao_id': self.cfop_consig.id})

        self.assertEqual(posicao.nfe_cfop_interno_id.code, '5917')
        self.assertEqual(posicao.nfe_cfop_externo_id.code, '6917')

    def test_imposto_da_linha_ganha_da_posicao_fiscal(self):
        """O imposto é por LINHA, a posição fiscal é da nota. Uma remessa pode
        misturar consignação e bonificação, e cabeçalho não desempata linha."""
        posicao = self.env['account.fiscal.position'].create({
            'name': 'Bonificacao', 'company_id': self.company.id,
            'nfe_operacao_id': operacao_de(self.env, '910', 'saida').id})
        move = self._fatura(posicao=posicao, imposto=self.imposto_consig)

        self.assertEqual(move._focus_build_payload()['items'][0]['cfop'], '5917')

    def test_posicao_sem_operacao_nao_derruba_a_tela(self):
        """A maioria das posições herdadas do legado não tem operação. Um
        `ensure_one()` num recordset vazio derrubava a lista inteira de Posições
        Fiscais com 'Expected singleton'."""
        posicao = self.env['account.fiscal.position'].create({
            'name': 'Sem operacao', 'company_id': self.company.id})

        self.assertFalse(posicao.nfe_cfop_interno_id)
        self.assertFalse(posicao.nfe_cfop_externo_id)
        self.assertIsNone(self.env['nfe.operacao'].cfop_para('interna'))
        self.assertFalse(self.env['nfe.operacao'].cfop_record('interna'))
