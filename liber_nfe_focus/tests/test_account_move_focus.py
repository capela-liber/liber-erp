# -*- coding: utf-8 -*-
"""Testes do efeito no banco: fatura -> payload -> status.

Contra um banco de teste de verdade, sem mockar o ORM. O que é mockado é só a
Focus (a rede), via um cliente falso injetado no lugar do real.
"""

from decimal import Decimal
from unittest.mock import patch

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models import nfe_payload

# Um ISBN que não é de livro nenhum. O código de barras é único por empresa no
# Odoo, e um ISBN real põe o teste em rota de colisão com o catálogo do banco em
# que ele roda -- foi o que aconteceu quando a suíte encontrou o exemplar de
# verdade. O prefixo 978-0-00-000000 é sintaticamente válido (o dígito 2 fecha o
# EAN-13) e não pertence a editora alguma.
ISBN_DE_TESTE = '9780000000002'


def preparar_documento_latam(move):
    """Dá um tipo de documento à fatura quando o `l10n_br` do Odoo está por perto.

    Este módulo emite a NFe pela Focus e não usa a cadeia fiscal do Odoo, mas
    nada impede que o `l10n_br` esteja instalado no mesmo banco -- ele entra
    sozinho assim que a empresa vira brasileira. Quando entra, o
    `l10n_latam_invoice_document` passa a exigir tipo de documento em toda
    fatura postada, e sem isto os testes quebram por um motivo que não tem nada
    a ver com o que eles testam. O tipo 55 é a própria NF-e.
    """
    if 'l10n_latam_document_type_id' not in move._fields:
        return
    if not move.journal_id.l10n_latam_use_documents:
        return
    tipo = move.env['l10n_latam.document.type'].search(
        [('code', '=', '55'), ('country_id.code', '=', 'BR')], limit=1)
    if tipo:
        move.l10n_latam_document_type_id = tipo


def cfop_de(env, code, **vals):
    """Pega o CFOP pelo código, ou cria se não houver.

    A tabela oficial do CONFAZ vem com o módulo e o código é único: um
    `create` cru quebraria em qualquer banco onde o módulo esteja instalado —
    que são todos.
    """
    cfop = env['nfe.cfop'].search([('code', '=', code)], limit=1)
    if cfop:
        if vals:
            cfop.write(vals)
        return cfop
    return env['nfe.cfop'].create(dict(vals, code=code))


def operacao_de(env, code, sentido='saida', **vals):
    """Pega a operação pelo sufixo e sentido, ou cria.

    As operações da casa vêm com o módulo; o par (sufixo, sentido) é único.
    """
    op = env['nfe.operacao'].search(
        [('code', '=', code), ('sentido', '=', sentido)], limit=1)
    if op:
        if vals:
            op.write(vals)
        return op
    return env['nfe.operacao'].create(
        dict(vals, code=code, sentido=sentido, name=vals.get('name') or code))


class FakeFocusClient(object):
    """Cliente falso: grava o que foi pedido e devolve o que o teste mandar."""

    def __init__(self, resposta=None, erro=None):
        self.resposta = resposta or {'status': 'processando_autorizacao'}
        self.erro = erro
        self.emissoes = []

    def emitir_nfe(self, ref, payload):
        if self.erro:
            raise self.erro
        self.emissoes.append((ref, payload))
        return self.resposta

    def consultar_nfe(self, ref, completa=True):
        return self.resposta

    def baixar(self, caminho):
        return b'<nfeProc/>'


@tagged('post_install', '-at_install', 'focus_nfe')
class TestAccountMoveFocus(AccountTestInvoicingCommon):

    # O plano de contas é fixado de propósito. Sem isto, o `AccountTestInvoicingCommon`
    # adivinha o plano pelo país da empresa que ele mesmo cria -- e com a
    # localização brasileira instalada essa empresa nasce no Brasil, o que traz
    # junto o `l10n_br` do Odoo e a exigência de tipo de documento LATAM em toda
    # fatura postada. Estes testes são sobre o payload da Focus, não sobre o
    # plano de contas: o genérico serve e não muda de baixo deles.
    chart_template = 'generic_coa'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Nada de dados de demonstração: tudo o que o teste precisa nasce aqui.
        cls.company = cls.env.company
        cls.company.write({
            'vat': '12345678000195',
            'focus_ambiente': 'homologacao',
            'focus_token_homologacao': 'tok-teste',
            'focus_regime_tributario': '3',
            'focus_ncm_padrao': '49019900',
            'focus_codigo_beneficio_fiscal': 'SP070130',
        })
        cls.company.partner_id.write({
            'street': 'Rua das Acácias',
            'nfe_numero': '100',
            'nfe_bairro': 'Centro',
            'city': 'São Paulo',
            'zip': '02055-060',
            'state_id': cls.env.ref('base.state_br_sp').id,
            'country_id': cls.env.ref('base.br').id,
            'nfe_inscricao_estadual': '111222333444',
        })

        # Os CFOPs vêm da tabela oficial do CONFAZ, que o módulo instala: aqui
        # se pega o que existe, não se cria outro -- o código é único.
        cls.cfop_interno = operacao_de(cls.env, '102', 'saida')
        cls.cfop_fora = operacao_de(cls.env, '102', 'saida')
        cls.company.write({
            'focus_operacao_padrao_id': cls.cfop_interno.id,
        })

        cls.cliente = cls.env['res.partner'].create({
            'name': 'Livraria Exemplo',
            'vat': '98765432000198',
            'street': 'Rua dos Ipês',
            'nfe_numero': '915',
            'nfe_bairro': 'Pinheiros',
            'city': 'São Paulo',
            'zip': '05416-011',
            'state_id': cls.env.ref('base.state_br_sp').id,
            'country_id': cls.env.ref('base.br').id,
            'nfe_inscricao_estadual': '111222333444',
            'nfe_indicador_ie': '1',
        })

        cls.livro = cls.env['product.product'].create({
            'name': 'Grande Sertão: Veredas',
            'default_code': 'LIV-001',
            'type': 'consu',
            'list_price': 89.90,
            'nfe_ncm': '49019900',
            'nfe_origem': '0',
        })


    def _fatura(self, partner=None, quantidade=3, preco=89.90, post=True):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': (partner or self.cliente).id,
            'invoice_date': '2026-07-30',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.livro.id,
                'name': self.livro.name,
                'quantity': quantidade,
                'price_unit': preco,
                'tax_ids': [(5, 0, 0)],
            })],
        })
        preparar_documento_latam(move)
        if post:
            move.action_post()
        return move

    # -- caminho feliz -------------------------------------------------
    def test_payload_da_fatura_esta_completo(self):
        payload = self._fatura()._focus_build_payload()

        self.assertEqual(nfe_payload.missing_fields(payload), [])
        self.assertEqual(payload['cnpj_emitente'], '12345678000195')
        self.assertEqual(payload['cnpj_destinatario'], '98765432000198')
        self.assertEqual(payload['items'][0]['cfop'], '5102')
        self.assertEqual(payload['items'][0]['codigo_ncm'], '49019900')
        self.assertEqual(payload['valor_total'], '269.70')

    def test_cfop_segue_a_uf_do_destinatario(self):
        de_fora = self.cliente.copy({
            'name': 'Livraria Carioca',
            'state_id': self.env.ref('base.state_br_rj').id,
            # O CNPJ vai explícito porque a localização da OCA, quando
            # instalada, apaga o CNPJ na cópia de parceiro brasileiro -- e com
            # razão, CNPJ é único. Duas livrarias diferentes têm CNPJs
            # diferentes de qualquer jeito.
            'vat': '45678901000175',
        })

        payload = self._fatura(partner=de_fora)._focus_build_payload()

        self.assertEqual(payload['items'][0]['cfop'], '6102')
        self.assertEqual(payload['local_destino'], nfe_payload.DESTINO_INTERESTADUAL)

    def test_cfop_da_linha_ganha_do_padrao_da_empresa(self):
        """Uma nota pode misturar operações; a linha decide."""
        bonificacao = self.env['nfe.cfop'].search([('code', '=', '5910')], limit=1)
        move = self._fatura(post=False)
        move.invoice_line_ids[0].nfe_cfop_id = bonificacao
        move.action_post()

        payload = move._focus_build_payload()

        self.assertEqual(payload['items'][0]['cfop'], '5910')

    def test_homologacao_troca_o_nome_do_destinatario(self):
        """A SEFAZ exige esta razão social em homologação e rejeita nota de
        teste com nome de cliente real. A troca é no payload, não no cadastro:
        o cliente continua sendo quem é."""
        payload = self._fatura()._focus_build_payload()

        self.assertEqual(payload['nome_destinatario'],
                         nfe_payload.NOME_DESTINATARIO_HOMOLOGACAO)
        self.assertEqual(self.cliente.name, 'Livraria Exemplo')
        # O CNPJ continua o do cliente: só o nome é imposto.
        self.assertEqual(payload['cnpj_destinatario'], '98765432000198')

    def test_producao_usa_o_nome_real_do_cliente(self):
        self.company.write({
            'focus_ambiente': 'producao', 'focus_token_producao': 'tok-prod'})

        payload = self._fatura()._focus_build_payload()

        self.assertEqual(payload['nome_destinatario'], 'Livraria Exemplo')

    def test_cbenef_da_empresa_entra_no_item(self):
        payload = self._fatura()._focus_build_payload()

        self.assertEqual(payload['items'][0]['codigo_beneficio_fiscal'],
                         'SP070130')

    def test_cbenef_do_produto_ganha_do_da_empresa(self):
        self.livro.product_tmpl_id.nfe_codigo_beneficio_fiscal = 'SP070200'

        payload = self._fatura()._focus_build_payload()

        self.assertEqual(payload['items'][0]['codigo_beneficio_fiscal'],
                         'SP070200')

    # -- a operação fiscal vem do CFOP ---------------------------------
    def test_cfop_da_nota_dita_natureza_e_finalidade(self):
        """Uma remessa em consignação não é uma venda. Sem isto ela sairia com
        natureza 'Venda de mercadoria', que é falso no DANFE."""
        consignacao = self.env['nfe.cfop'].search([('code', '=', '5917')], limit=1)
        move = self._fatura(post=False)
        move.nfe_cfop_id = consignacao
        move.action_post()

        payload = move._focus_build_payload()

        self.assertEqual(payload['natureza_operacao'], 'Remessa em consignacao mercantil')
        self.assertEqual(payload['items'][0]['cfop'], '5917')
        self.assertEqual(payload['consumidor_final'], 0)

    # -- devolução simbólica -------------------------------------------
    def _cfop_devolucao(self):
        # CFOP de entrada escolhido à mão: a devolução aponta a nota de origem.
        return self.env['nfe.cfop'].search([('code', '=', '1918')], limit=1)

    def test_devolucao_sai_como_entrada_e_referencia_a_original(self):
        """1918 é ENTRADA (a mercadoria volta para nós) mesmo sendo nós a
        emitir a nota, e precisa apontar o que está devolvendo."""
        original = self._fatura()
        original._focus_aplicar_resposta(
            {'status': 'autorizado', 'chave_nfe': '2' * 44})

        move = self._fatura(post=False)
        move.write({
            'nfe_cfop_id': self._cfop_devolucao().id,
            'focus_nota_referenciada_id': original.id,
            'focus_chave_referenciada': original.nfe_key,
        })
        move.action_post()

        payload = move._focus_build_payload()

        self.assertEqual(payload['tipo_documento'], nfe_payload.ENTRADA)
        self.assertEqual(payload['finalidade_emissao'],
                         nfe_payload.FINALIDADE_DEVOLUCAO)
        self.assertEqual(payload['natureza_operacao'],
                         'Devolucao de mercadoria remetida em consignacao')
        # O cabeçalho NÃO leva a referência: com a do item ela seria duplicada
        # e a SEFAZ recusa os dois níveis juntos.
        self.assertNotIn('notas_referenciadas', payload)
        # Referência POR ITEM: sem ela a SEFAZ recusa com "não possui documento
        # fiscal referenciado por item", mesmo com a nota referenciada no
        # cabeçalho.
        item = payload['items'][0]
        self.assertEqual(item['chave_acesso_dfe_referenciado'], '2' * 44)
        self.assertEqual(item['numero_item_dfe_referenciado'], '1')

    def test_item_referenciado_a_mao_ganha_da_busca_por_produto(self):
        original = self._fatura()
        original._focus_aplicar_resposta(
            {'status': 'autorizado', 'chave_nfe': '5' * 44})
        move = self._fatura(post=False)
        move.write({
            'nfe_cfop_id': self._cfop_devolucao().id,
            'focus_nota_referenciada_id': original.id,
        })
        move.invoice_line_ids[0].nfe_item_referenciado = 7
        move.action_post()

        item = move._focus_build_payload()['items'][0]

        self.assertEqual(item['numero_item_dfe_referenciado'], '7')

    def test_venda_comum_nao_leva_referencia_por_item(self):
        """Fora de uma devolução o campo é indevido."""
        item = self._fatura()._focus_build_payload()['items'][0]

        self.assertNotIn('chave_acesso_dfe_referenciado', item)

    def test_devolucao_sem_nota_de_origem_e_barrada(self):
        """Sem a chave da nota devolvida a SEFAZ não sabe o que se devolve."""
        move = self._fatura(post=False)
        move.nfe_cfop_id = self._cfop_devolucao()
        move.action_post()

        with self.assertRaises(UserError) as ctx:
            move._focus_build_payload()

        self.assertIn('nota de origem', str(ctx.exception))

    def test_chave_da_origem_vem_sozinha_ao_escolher_a_nota(self):
        original = self._fatura()
        original._focus_aplicar_resposta(
            {'status': 'autorizado', 'chave_nfe': '4' * 44})
        move = self._fatura(post=False)

        move.focus_nota_referenciada_id = original
        move._onchange_focus_nota_referenciada_id()

        self.assertEqual(move.focus_chave_referenciada, '4' * 44)

    def test_venda_comum_continua_saindo_como_saida(self):
        payload = self._fatura()._focus_build_payload()

        self.assertEqual(payload['tipo_documento'], nfe_payload.SAIDA)
        self.assertNotIn('notas_referenciadas', payload)

    def test_cst_da_operacao_ganha_do_regime_da_empresa(self):
        """Um CFOP escolhido à mão recupera a configuração pela OPERAÇÃO: é o
        sufixo que carrega CST e cBenef, não o código de quatro dígitos."""
        operacao_de(self.env, '910', 'saida', cst_icms='40', cbenef='SP070199')
        cfop = self.env['nfe.cfop'].search([('code', '=', '5910')], limit=1)
        move = self._fatura(post=False)
        move.nfe_cfop_id = cfop
        move.action_post()

        item = move._focus_build_payload()['items'][0]

        self.assertEqual(item['icms_situacao_tributaria'], '40')
        self.assertEqual(item['codigo_beneficio_fiscal'], 'SP070199')

    def test_cfop_da_linha_ganha_do_cfop_da_nota(self):
        """Uma nota pode misturar operações, e cada linha leva a sua."""
        operacao_de(self.env, '917', 'saida',
                    natureza_operacao='Remessa em consignacao mercantil')
        operacao_de(self.env, '910', 'saida', cst_icms='40')
        Cfop = self.env['nfe.cfop']
        move = self._fatura(post=False)
        move.nfe_cfop_id = Cfop.search([('code', '=', '5917')], limit=1)
        move.invoice_line_ids[0].nfe_cfop_id = Cfop.search(
            [('code', '=', '5910')], limit=1)
        move.action_post()

        payload = move._focus_build_payload()

        # A natureza continua sendo a da nota; o item é que segue seu CFOP.
        self.assertEqual(payload['natureza_operacao'], 'Remessa em consignacao mercantil')
        self.assertEqual(payload['items'][0]['cfop'], '5910')
        self.assertEqual(payload['items'][0]['icms_situacao_tributaria'], '40')

    def test_sem_cfop_na_nota_cai_no_padrao_da_empresa(self):
        payload = self._fatura()._focus_build_payload()

        self.assertEqual(payload['items'][0]['cfop'], '5102')
        # A natureza vem do CFOP, que o módulo já configura -- não do texto
        # genérico da empresa.
        self.assertEqual(payload['natureza_operacao'],
                         'Venda de mercadoria adquirida de terceiros')

    def test_emissao_grava_referencia_ambiente_e_status(self):
        move = self._fatura()
        falso = FakeFocusClient({'status': 'processando_autorizacao'})

        with patch.object(type(self.company), '_focus_client', return_value=falso):
            move.action_focus_emitir()

        self.assertEqual(move.focus_status, 'processando_autorizacao')
        self.assertEqual(move.focus_ambiente, 'homologacao')
        self.assertTrue(move.focus_ref)
        self.assertEqual(falso.emissoes[0][0], move.focus_ref)

    def test_referencia_e_deterministica(self):
        """Ela é recalculável porque o rollback de um envio que estourou apaga
        o campo -- e a Focus deduplica pela referência, não emite duas vezes."""
        move = self._fatura()

        self.assertEqual(move._focus_build_ref(), move._focus_build_ref())
        self.assertIn(str(move.id), move._focus_build_ref())

    def test_rejeicao_deriva_ref_nova_na_reemissao(self):
        """A Focus congela a ref na nota rejeitada: reemitir com a mesma ref
        devolve a recusa velha para sempre. Depois de `erro_autorizacao` a
        ref avança com -R2, e é a nova que vai no POST."""
        move = self._fatura()
        falso = FakeFocusClient({'status': 'processando_autorizacao'})

        with patch.object(type(self.company), '_focus_client',
                          return_value=falso):
            move.action_focus_emitir()
            ref_original = move.focus_ref

            move.write({'focus_status': 'erro_autorizacao'})
            move.action_focus_emitir()

        self.assertEqual(move.focus_ref, '%s-R2' % ref_original)
        self.assertEqual(falso.emissoes[-1][0], '%s-R2' % ref_original,
                         "o POST não foi com a ref nova")

    def test_rejeicoes_sucessivas_incrementam_o_sufixo(self):
        """-R2 rejeitada vira -R3, não -R2-R2."""
        move = self._fatura()
        move.write({'focus_ref': 'EDLAB-1-77-R2',
                    'focus_status': 'erro_autorizacao'})

        self.assertEqual(move._focus_ref_para_emissao(), 'EDLAB-1-77-R3')

    def test_repeticao_sem_rejeicao_mantem_a_ref(self):
        """O sufixo só anda DEPOIS de rejeição definitiva: a repetição da
        mesma tentativa (rollback, clique duplo) cai na mesma ref, que é a
        proteção contra nota duplicada."""
        move = self._fatura()
        self.assertEqual(move._focus_ref_para_emissao(),
                         move._focus_build_ref())

        move.write({'focus_ref': 'EDLAB-1-77', 'focus_status': 'nao_enviado'})
        self.assertEqual(move._focus_ref_para_emissao(), 'EDLAB-1-77')

    def test_prefixo_nfe_da_chave_e_removido(self):
        """A Focus devolve a chave prefixada com 'NFe', como no código de
        barras do DANFE. O nfe_key exige 44 dígitos e nada mais: sem limpar, a
        ValidationError derruba a consulta de uma nota AUTORIZADA."""
        move = self._fatura()

        move._focus_aplicar_resposta({
            'status': 'autorizado', 'chave_nfe': 'NFe' + '7' * 44})

        self.assertEqual(move.nfe_key, '7' * 44)

    def test_chave_com_tamanho_errado_nao_e_gravada(self):
        """Chave malformada não entra no índice, mas o status vale."""
        move = self._fatura()

        move._focus_aplicar_resposta({
            'status': 'autorizado', 'chave_nfe': 'NFe123'})

        self.assertFalse(move.nfe_key)
        self.assertEqual(move.focus_status, 'autorizado')

    def test_autorizacao_guarda_a_chave_de_acesso_na_fatura(self):
        move = self._fatura()
        chave = '3' * 44

        move._focus_aplicar_resposta({
            'status': 'autorizado',
            'chave_nfe': chave,
            'numero': '123',
            'serie': '1',
            'protocolo': '135260000123456',
        })

        # A chave é o elo com o liber_nfe_xml: emitida e recebida viram a
        # mesma coisa para o resto do sistema.
        self.assertEqual(move.nfe_key, chave)
        self.assertEqual(move.focus_status, 'autorizado')
        self.assertEqual(move.focus_numero, '123')

    def test_consulta_atualiza_o_status(self):
        move = self._fatura()
        move.write({'focus_ref': 'EDLAB-TESTE-1', 'focus_ambiente': 'homologacao'})
        falso = FakeFocusClient({'status': 'autorizado', 'chave_nfe': '4' * 44})

        with patch.object(type(move), '_focus_client_da_nota', return_value=falso):
            move.action_focus_consultar()

        self.assertEqual(move.focus_status, 'autorizado')
        self.assertEqual(move.nfe_key, '4' * 44)

    # -- casos de erro -------------------------------------------------
    def test_nao_se_emite_nfe_de_rascunho(self):
        move = self._fatura(post=False)

        with self.assertRaises(UserError):
            move.action_focus_emitir()

    def test_rejeicao_da_focus_vira_mensagem_para_o_usuario(self):
        from ..models.focus_client import FocusValidationError
        move = self._fatura()
        falso = FakeFocusClient(erro=FocusValidationError(
            'Rejeicao: IE do destinatario invalida'))

        with patch.object(type(self.company), '_focus_client', return_value=falso):
            with self.assertRaises(UserError) as ctx:
                move.action_focus_emitir()

        self.assertIn('IE do destinatario invalida', str(ctx.exception))

    def test_fatura_sem_cfop_configurado_explica_o_que_falta(self):
        self.company.write({
            'focus_operacao_padrao_id': False,
        })
        move = self._fatura()

        with self.assertRaises(UserError) as ctx:
            move._focus_build_payload()

        self.assertIn('operação fiscal', str(ctx.exception))

    def test_destinatario_sem_endereco_e_barrado_antes_da_chamada(self):
        sem_endereco = self.env['res.partner'].create({
            'name': 'Cliente sem endereço', 'vat': '98765432000198'})
        move = self._fatura(partner=sem_endereco)

        with self.assertRaises(UserError) as ctx:
            move._focus_build_payload()

        self.assertIn('municipio_destinatario', str(ctx.exception))

    def test_chave_de_nota_rejeitada_nao_entra_no_indice(self):
        """Gravar a chave de uma nota que a SEFAZ recusou envenenaria o índice
        de chaves do liber_nfe_xml, que assume nota existente."""
        move = self._fatura()

        move._focus_aplicar_resposta({
            'status': 'erro_autorizacao',
            'chave_nfe': '5' * 44,
            'mensagem_sefaz': 'Rejeicao: duplicidade de NF-e',
        })

        self.assertFalse(move.nfe_key)
        self.assertEqual(move.focus_status, 'erro_autorizacao')
        self.assertIn('duplicidade', move.focus_mensagem)

    def test_reenvio_de_nota_ja_autorizada_e_barrado(self):
        move = self._fatura()
        move._focus_aplicar_resposta({'status': 'autorizado', 'chave_nfe': '6' * 44})

        with self.assertRaises(UserError):
            move.action_focus_emitir()

    def test_empresa_sem_token_diz_qual_ambiente_falta(self):
        self.company.focus_token_homologacao = False
        move = self._fatura()

        with self.assertRaises(UserError) as ctx:
            move.company_id._focus_client()

        self.assertIn('homologacao', str(ctx.exception))

    def test_desconto_da_fatura_chega_na_nota(self):
        """O desconto da linha tem de aparecer no DANFE, e o total da nota tem
        de ser o que a fatura cobra."""
        move = self._fatura(post=False)
        move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product').discount = 10.0
        move.action_post()

        payload = move._focus_build_payload()

        # 3 x 89,90 = 269,70 bruto; 10% = 26,97 de desconto
        self.assertEqual(payload['items'][0]['valor_bruto'], '269.70')
        self.assertEqual(payload['items'][0]['valor_desconto'], '26.97')
        self.assertEqual(payload['valor_desconto'], '26.97')
        self.assertEqual(payload['valor_total'], '242.73')

    def test_total_da_nota_bate_com_o_da_fatura(self):
        """O que a nota declara e o que se cobra têm de ser o mesmo número."""
        move = self._fatura(post=False)
        move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product').discount = 15.0
        move.action_post()

        payload = move._focus_build_payload()

        self.assertEqual(payload['valor_total'],
                         nfe_payload.money(move.amount_total))

    def test_sem_desconto_o_campo_nao_vai(self):
        payload = self._fatura()._focus_build_payload()

        self.assertNotIn('valor_desconto', payload['items'][0])
        self.assertEqual(payload['valor_desconto'], '0.00')

    # -- frete e transportadora ------------------------------------------
    def _transportadora(self):
        return self.env['res.partner'].create({
            'name': 'Transportes Andorinha',
            'is_company': True,
            'vat': '11222333000181',
            'street': 'Rua das Gaivotas',
            'nfe_numero': '10',
            'nfe_bairro': 'Centro',
            'city': 'São Paulo',
            'state_id': self.env.ref('base.state_br_sp').id,
            'country_id': self.env.ref('base.br').id,
            'nfe_inscricao_estadual': '111222333555',
        })

    def test_modalidade_e_transportadora_viajam_na_nota(self):
        move = self._fatura(post=False)
        move.write({'nfe_modalidade_frete': '0',
                    'nfe_transportadora_id': self._transportadora().id})
        move.action_post()

        payload = move._focus_build_payload()

        self.assertEqual(payload['modalidade_frete'],
                         nfe_payload.FRETE_EMITENTE)
        self.assertEqual(payload['nome_transportador'],
                         'Transportes Andorinha')
        self.assertEqual(payload['cnpj_transportador'], '11222333000181')
        self.assertEqual(payload['inscricao_estadual_transportador'],
                         '111222333555')
        self.assertEqual(payload['endereco_transportador'],
                         'Rua das Gaivotas, 10')
        self.assertEqual(payload['uf_transportador'], 'SP')

    def test_fatura_sem_frete_sai_sem_ocorrencia(self):
        """O comportamento de sempre: nada preenchido, modalidade 9."""
        payload = self._fatura()._focus_build_payload()

        self.assertEqual(payload['modalidade_frete'], nfe_payload.FRETE_SEM)
        self.assertNotIn('nome_transportador', payload)

    def test_transportadora_nao_viaja_sem_ocorrencia_de_transporte(self):
        """Modalidade 9 cala o grupo transportador, mesmo preenchido."""
        move = self._fatura(post=False)
        move.write({'nfe_modalidade_frete': '9',
                    'nfe_transportadora_id': self._transportadora().id})
        move.action_post()

        payload = move._focus_build_payload()

        self.assertEqual(payload['modalidade_frete'], nfe_payload.FRETE_SEM)
        self.assertNotIn('nome_transportador', payload)
        self.assertNotIn('cnpj_transportador', payload)

@tagged('post_install', '-at_install', 'focus_nfe')
class TestResPartnerFocus(AccountTestInvoicingCommon):

    chart_template = 'generic_coa'

    def test_numero_e_lido_do_fim_do_logradouro(self):
        partner = self.env['res.partner'].create({
            'name': 'Teste', 'street': 'Rua dos Ipês, 915'})

        self.assertEqual(partner.nfe_numero, '915')

    def test_endereco_sem_numero_vira_sem_numero(self):
        partner = self.env['res.partner'].create({
            'name': 'Teste', 'street': 'Rodovia Anhanguera km 12'})

        self.assertEqual(partner.nfe_numero, 'S/N')

    def test_numero_digitado_a_mao_nao_e_sobrescrito(self):
        partner = self.env['res.partner'].create({
            'name': 'Teste', 'street': 'Rua A, 100', 'nfe_numero': '100-B'})

        partner.street = 'Rua A, 200'

        self.assertEqual(partner.nfe_numero, '100-B')

    def test_inscricao_estadual_com_letras_e_recusada(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({
                'name': 'Teste', 'nfe_inscricao_estadual': 'ISENTO'})


@tagged('post_install', '-at_install', 'focus_nfe')
class TestNotaServivel(TestAccountMoveFocus):
    """O que separa 'a SEFAZ aceita' de 'a nota serve ao cliente'."""

    def test_isbn_do_produto_vai_para_a_nota(self):
        self.livro.barcode = ISBN_DE_TESTE
        self.livro.product_tmpl_id.default_code = False
        self.company.focus_codigo_produto = 'barras' 

        item = self._fatura()._focus_build_payload()['items'][0]

        # Sem referência interna, o ISBN vale como código do produto — melhor
        # que o id do registro, que não diz nada a quem recebe.
        self.assertEqual(item['codigo_produto'], ISBN_DE_TESTE)
        self.assertEqual(item['codigo_barras_comercial'], ISBN_DE_TESTE)
        self.assertEqual(item['codigo_barras_tributavel'], ISBN_DE_TESTE)

    def test_referencia_interna_quando_a_casa_prefere_a_dela(self):
        self.livro.barcode = ISBN_DE_TESTE
        self.company.focus_codigo_produto = 'interno'

        item = self._fatura()._focus_build_payload()['items'][0]

        self.assertEqual(item['codigo_produto'], 'LIV-001')
        self.assertEqual(item['codigo_barras_comercial'], ISBN_DE_TESTE)

    def test_unidade_sai_como_sigla_e_nao_como_rotulo(self):
        """O nome da unidade no Odoo é rótulo de interface: sai 'Units'."""
        item = self._fatura()._focus_build_payload()['items'][0]

        self.assertEqual(item['unidade_comercial'], 'UN')

    def test_sigla_configurada_na_unidade_e_respeitada(self):
        self.livro.uom_id.nfe_unidade = 'CX'

        item = self._fatura()._focus_build_payload()['items'][0]

        self.assertEqual(item['unidade_comercial'], 'CX')

    def test_referencia_lixo_de_migracao_cai_fora(self):
        """`default_code` valendo "0" é sujeira de migração: não identifica
        nada, e uma nota com cProd=0 é inútil para quem a recebe."""
        self.livro.barcode = ISBN_DE_TESTE
        self.livro.product_tmpl_id.default_code = '0'
        self.company.focus_codigo_produto = 'interno'

        item = self._fatura()._focus_build_payload()['items'][0]

        self.assertEqual(item['codigo_produto'], ISBN_DE_TESTE)

    def _fatura_com_vencimento(self, vencimento):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id,
            'invoice_date': '2026-07-30', 'invoice_date_due': vencimento,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.livro.id, 'name': self.livro.name,
                'quantity': 3, 'price_unit': 89.90, 'tax_ids': [(5, 0, 0)]})]})
        preparar_documento_latam(move)
        move.action_post()
        return move

    def test_a_vista_nao_leva_duplicata(self):
        """A SEFAZ recusa: "Dados de cobrança não devem ser informados para
        pagamento à vista". Duplicata só é duplicata se vence depois."""
        move = self._fatura_com_vencimento('2026-07-30')   # mesmo dia

        payload = move._focus_build_payload()

        self.assertNotIn('duplicatas', payload)
        self.assertEqual(payload['formas_pagamento'][0]['forma_pagamento'], '01')

    def test_forma_a_vista_configurada_e_respeitada(self):
        self.company.focus_forma_pagamento_vista = '17'   # PIX

        payload = self._fatura_com_vencimento('2026-07-30')._focus_build_payload()

        self.assertEqual(payload['formas_pagamento'][0]['forma_pagamento'], '17')

    def test_a_prazo_leva_duplicata_e_forma_14(self):
        """Vencimento depois da emissão: aí sim é duplicata mercantil."""
        payload = self._fatura_com_vencimento('2026-08-30')._focus_build_payload()

        self.assertEqual(len(payload['duplicatas']), 1)
        self.assertEqual(payload['duplicatas'][0]['data_vencimento'], '2026-08-30')
        self.assertEqual(payload['formas_pagamento'][0]['forma_pagamento'], '14')
        self.assertEqual(payload['valor_liquido_fatura'], '269.70')

    def test_o_centavo_do_arredondamento_global_nao_vira_rejeicao(self):
        """Rejeição 866 na n-1, em 14/08/2026, em duas notas.

        São dois arredondamentos do mesmo dinheiro. A NFe soma os itens JÁ
        arredondados -- é o que a SEFAZ confere. O Odoo, com a empresa
        arredondando globalmente (que é como as seis da casa estão), soma os
        valores exatos das linhas e arredonda no fim, e depois joga a sobra na
        conta de uma das linhas para o lançamento fechar.

        Três linhas de 2 x 69,90 com 52%: 67,104 por linha, que vira 67,10 no
        item e 201,31 no rodapé do Odoo contra 201,30 na nota. A cobrança saía
        um centavo maior que a nota, e a SEFAZ pede troco -- que numa venda a
        prazo não existe.

        Com uma linha só nada disso aparece: é preciso mais de uma para haver
        sobra a distribuir.
        """
        self.company.tax_calculation_rounding_method = 'round_globally'
        linha = {
            'product_id': self.livro.id, 'name': self.livro.name,
            'quantity': 2, 'price_unit': 69.90, 'discount': 52.0,
            'tax_ids': [(5, 0, 0)]}
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id,
            'invoice_date': '2026-07-30', 'invoice_date_due': '2026-11-12',
            'invoice_line_ids': [(0, 0, dict(linha)) for _ in range(3)]})
        preparar_documento_latam(move)
        move.action_post()
        # A divergência tem de existir de fato, senão o teste não prova nada.
        self.assertEqual(move.amount_total, 201.31)
        self.assertEqual(
            round(sum(move.invoice_line_ids.mapped('price_subtotal')), 2), 201.30)

        payload = move._focus_build_payload()

        total = Decimal(payload['valor_total'])
        self.assertEqual(total, Decimal('201.30'))
        pago = sum(Decimal(f['valor_pagamento'])
                   for f in payload['formas_pagamento'])
        self.assertLessEqual(pago, total)
        self.assertEqual(sum(Decimal(d['valor']) for d in payload['duplicatas']),
                         Decimal(payload['valor_liquido_fatura']))
        self.assertEqual(Decimal(payload['valor_liquido_fatura']), total)


@tagged('post_install', '-at_install', 'focus_nfe')
class TestHistoricoSefaz(TestAccountMoveFocus):
    """O que a SEFAZ respondeu tem de sobreviver à tela que o mostrou."""

    def _mensagens(self, move):
        return self.env['mail.message'].search([
            ('model', '=', 'account.move'), ('res_id', '=', move.id)])

    def test_autorizacao_deixa_rastro_com_chave_e_protocolo(self):
        move = self._fatura()

        move._focus_aplicar_resposta({
            'status': 'autorizado', 'chave_nfe': '7' * 44, 'numero': '42',
            'serie': '9', 'protocolo': '135260000000001',
            'mensagem_sefaz': 'Autorizado o uso da NF-e'})

        corpo = ' '.join(self._mensagens(move).mapped('body'))
        self.assertIn('7' * 44, corpo)
        self.assertIn('135260000000001', corpo)
        self.assertIn('autorizada', corpo)

    def test_rejeicao_deixa_rastro_com_o_motivo(self):
        """Sem isto a rejeição sumia com a tela, e semanas depois ninguém sabia
        por que aquela nota nunca saiu."""
        move = self._fatura()

        move._focus_aplicar_resposta({
            'status': 'erro_autorizacao', 'status_sefaz': '539',
            'mensagem_sefaz': 'Rejeicao: Duplicidade de NF-e'})

        corpo = ' '.join(self._mensagens(move).mapped('body'))
        self.assertIn('539', corpo)
        self.assertIn('Duplicidade', corpo)
        self.assertIn('rejeitada', corpo)

    def test_consulta_repetida_nao_polui_o_historico(self):
        """O cron consulta de dez em dez minutos: repetir a mesma linha a cada
        volta transformaria o histórico em ruído."""
        move = self._fatura()
        resposta = {'status': 'autorizado', 'chave_nfe': '8' * 44}
        move._focus_aplicar_resposta(resposta)
        antes = len(self._mensagens(move))

        move._focus_aplicar_resposta(resposta)
        move._focus_aplicar_resposta(resposta)

        self.assertEqual(len(self._mensagens(move)), antes)

    def test_ainda_processando_nao_gera_mensagem(self):
        move = self._fatura()
        antes = len(self._mensagens(move))

        move._focus_aplicar_resposta({'status': 'processando_autorizacao'})

        self.assertEqual(len(self._mensagens(move)), antes)

    def test_a_mensagem_e_html_de_verdade_e_nao_tags_a_mostra(self):
        """Desde o 16 o Odoo escapa corpo que não seja Markup — e a mensagem
        sairia com `&lt;p&gt;` na cara do usuário."""
        move = self._fatura()

        move._focus_aplicar_resposta({'status': 'autorizado', 'chave_nfe': '9' * 44})

        corpo = ' '.join(self._mensagens(move).mapped('body'))
        self.assertIn('<b>', corpo)
        self.assertNotIn('&lt;b&gt;', corpo)

    def test_a_mensagem_da_sefaz_nao_vira_injecao(self):
        """O `%` do Markup escapa os valores: texto da SEFAZ é dado, não HTML."""
        move = self._fatura()

        move._focus_aplicar_resposta({
            'status': 'erro_autorizacao',
            'mensagem_sefaz': 'Rejeicao <script>alert(1)</script>'})

        corpo = ' '.join(self._mensagens(move).mapped('body'))
        self.assertNotIn('<script>', corpo)
        self.assertIn('&lt;script&gt;', corpo)

    def test_pedido_vai_em_dados_adicionais(self):
        """O cliente casa a nota com o pedido dele, não com o número dela."""
        move = self._fatura()
        move.invoice_origin = 'S00123'
        move.narration = False

        self.assertEqual(move._focus_informacoes_adicionais(), 'Pedido: S00123')

    def test_observacao_da_fatura_acompanha_o_pedido(self):
        move = self._fatura()
        move.invoice_origin = 'S00123'
        move.narration = '<p>Entregar pela manhã</p>'

        texto = move._focus_informacoes_adicionais()
        self.assertIn('Pedido: S00123', texto)
        self.assertIn('Entregar pela manhã', texto)

    def test_sem_pedido_e_sem_observacao_nao_vai_nada(self):
        move = self._fatura()
        move.invoice_origin = False
        move.narration = False

        self.assertFalse(move._focus_informacoes_adicionais())

