# -*- coding: utf-8 -*-
"""A DANFE chega à transferência — e só a ela.

As empresas e o armazém são os do banco, não criados aqui: criar
``res.company`` num banco com ``account`` instalado quebra no NOT NULL de
``fiscalyear_last_day`` (lição de 07/2026).
"""
import base64
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.liber_nfe_focus.tests.test_account_move_focus import (
    operacao_de, preparar_documento_latam)
from odoo.addons.liber_nfe_picking.models import account_move as am

REPORT = 'liber_nfe_picking.report_picking_danfe'


def pdf_minimo(texto):
    """Um PDF de uma página, válido de verdade (xref calculado, não chutado).

    O teste do "imprimir dois juntos" passa pelo ``merge_pdf`` do Odoo, que
    PARSEIA os PDFs — um binário de mentira ali explode. Nos demais testes o
    conteúdo não importa, mas usar o mesmo gerador não custa.
    """
    conteudo = b'BT /F1 24 Tf 72 760 Td (%s) Tj ET' % texto.encode('latin-1')
    objetos = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
        b'/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length %d >>\nstream\n%s\nendstream' % (len(conteudo), conteudo),
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    corpo = b'%PDF-1.4\n'
    offsets = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(corpo))
        corpo += b'%d 0 obj\n%s\nendobj\n' % (i, obj)
    inicio_xref = len(corpo)
    xref = b'xref\n0 %d\n0000000000 65535 f \n' % (len(objetos) + 1)
    for off in offsets:
        xref += b'%010d 00000 n \n' % off
    return corpo + xref + (
        b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF'
        % (len(objetos) + 1, inicio_xref))


class TestNfePicking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Um armazém cuja empresa tem diário de venda: é a única condição
        # para o fluxo SO -> transferência -> fatura andar inteiro.
        Journal = cls.env['account.journal'].sudo()
        cls.wh = None
        for wh in cls.env['stock.warehouse'].sudo().search([]):
            if Journal.search_count([('type', '=', 'sale'),
                                     ('company_id', '=', wh.company_id.id)]):
                cls.wh = wh
                break
        assert cls.wh, "nenhum armazém com diário de venda no banco de teste"
        cls.company = cls.wh.company_id
        cls.env = cls.env(context=dict(
            cls.env.context, allowed_company_ids=cls.company.ids))

        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria do Teste DANFE',
            'company_id': False,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Livro do Teste DANFE',
            'type': 'consu',
            'invoice_policy': 'order',
            'list_price': 50.0,
        })

    def _pedido_faturado(self):
        """SO confirmado (gera a transferência) e faturado (gera a nota)."""
        so = self.env['sale.order'].with_company(self.company).create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'warehouse_id': self.wh.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 2,
                'price_unit': 50.0,
            })],
        })
        so.action_confirm()
        self.assertTrue(so.picking_ids, "o pedido confirmado tem de gerar transferência")
        move = so._create_invoices()
        move.write({
            'focus_ref': 'TESTREF-%s' % so.id,
            'focus_numero': '4242',
            'focus_status': 'autorizado',
        })
        return so, move

    CHAVE_XML = '35260712345678000195550010000009999000009999'

    def _pedido_com_nota_de_xml(self):
        """O formato Olist: venda confirmada e fatura LANÇADA que nasceu de um
        XML autorizado fora — nada de Focus (focus_status fica nao_enviado)."""
        so = self.env['sale.order'].with_company(self.company).create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'warehouse_id': self.wh.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': 50.0,
            })],
        })
        so.action_confirm()
        move = so._create_invoices()
        preparar_documento_latam(move)
        move.action_post()
        move.write({'nfe_key': self.CHAVE_XML})
        return so, move

    def test_nota_de_xml_carimba_o_picking(self):
        """Olist e afins: quando o painel ganha a fatura, a nota chega ao mov.

        Sem isso a logística ficava barrada no "Sem nota fiscal" para sempre —
        o carimbo normal é o gancho da autorização Focus, que a nota emitida
        fora nunca atravessa (EL-VG/OUT/01890, 18/08/2026)."""
        painel = self.env['nfe.xml.panel'].create({
            'key': self.CHAVE_XML, 'file_name': 'olist.xml',
            'status': 'imported'})
        so, move = self._pedido_com_nota_de_xml()
        self.assertEqual(move.nfe_xml_panel_id, painel,
                         "a chave de acesso é o elo fatura -> painel")
        self.assertFalse(so.picking_ids.nfe_move_id)

        painel.invoice_id = move

        self.assertEqual(so.picking_ids.nfe_move_id, move,
                         "a nota nascida de XML tem de chegar à transferência "
                         "sem Focus no caminho")

    def test_carimbo_de_segunda_chance_no_picking(self):
        """Movs de antes do gancho do painel: a impressão resolve na hora."""
        self.env['nfe.xml.panel'].create({
            'key': self.CHAVE_XML, 'file_name': 'olist.xml',
            'status': 'imported'})
        so, move = self._pedido_com_nota_de_xml()
        picking = so.picking_ids
        self.assertFalse(picking.nfe_move_id)

        picking._liber_carimbar_nota_de_xml()

        self.assertEqual(picking.nfe_move_id, move)

    def _anexa_danfe(self, move):
        return self.env['ir.attachment'].create({
            'name': '%s.pdf' % move.focus_ref,
            'datas': base64.b64encode(pdf_minimo('DANFE %s' % move.focus_ref)),
            'mimetype': 'application/pdf',
            'res_model': 'account.move',
            'res_id': move.id,
        })

    def _anexos_do_picking(self, picking):
        return self.env['ir.attachment'].search([
            ('res_model', '=', 'stock.picking'),
            ('res_id', '=', picking.id),
        ])

    # ------------------------------------------------------------------
    # caminho feliz: venda (S000)
    # ------------------------------------------------------------------
    def test_venda_danfe_chega_ao_picking(self):
        so, move = self._pedido_faturado()
        self._anexa_danfe(move)
        picking = so.picking_ids[0]
        mensagens_antes = len(picking.message_ids)

        move._liber_danfe_para_pickings()

        self.assertEqual(picking.nfe_move_id, move)
        self.assertTrue(picking.has_nfe)
        self.assertEqual(picking.nfe_numero, '4242')
        anexos = self._anexos_do_picking(picking)
        self.assertEqual(len(anexos), 1)
        self.assertEqual(anexos.name, '%s.pdf' % move.focus_ref)
        nova = picking.message_ids[:len(picking.message_ids) - mensagens_antes]
        self.assertTrue(any(m.attachment_ids for m in nova),
                        "a mensagem do chatter tem de carregar o PDF")

    def test_propagacao_e_idempotente(self):
        so, move = self._pedido_faturado()
        self._anexa_danfe(move)
        picking = so.picking_ids[0]

        move._liber_danfe_para_pickings()
        mensagens = len(picking.message_ids)
        move._liber_danfe_para_pickings()  # a consulta do cron repete o gancho

        self.assertEqual(len(self._anexos_do_picking(picking)), 1,
                         "repetir a consulta não pode duplicar o anexo")
        self.assertEqual(len(picking.message_ids), mensagens,
                         "repetir a consulta não pode duplicar a mensagem")

    # ------------------------------------------------------------------
    # a perna da remessa: sem linha ligada, o elo é o invoice_origin
    # ------------------------------------------------------------------
    def test_remessa_acha_picking_pelo_origin(self):
        so, move = self._pedido_faturado()
        self._anexa_danfe(move)
        # A nota REM/ nasce com linhas cruas: sem sale_line_ids. O
        # invoice_origin (nome do pedido) é o único elo — como no
        # action_generate_remessa_note do liber_soc_fiscal_br.
        move.invoice_line_ids.sale_line_ids = [(5, 0, 0)]
        self.assertEqual(move.invoice_origin, so.name)

        move._liber_danfe_para_pickings()

        self.assertEqual(so.picking_ids[0].nfe_move_id, move)

    def test_documento_que_nao_e_pedido_acha_o_picking_pelo_origin(self):
        """A remessa cujo documento de origem não é um pedido de venda.

        Descoberto pela bonificação em 31/08/2026: a ficha B000 cria a sua
        própria transferência e a sua própria nota de remessa, sem pedido
        nenhum entre as duas. A busca por pedido voltava vazia, a DANFE nunca
        chegava ao chatter do mov, e a logística embalava o pacote sem nota --
        com o filtro "Sem nota fiscal" jurando que ela não existia.

        O elo já estava no dado: os dois documentos carimbam o mesmo nome de
        origem. Este teste prende a regra geral, sem citar bonificação --
        qualquer documento futuro que gere remessa sem ser pedido entra por
        aqui.
        """
        so, move = self._pedido_faturado()
        self._anexa_danfe(move)
        # Desliga as duas pernas que sabem achar pedido: nem linha ligada, nem
        # invoice_origin que resolva para um sale.order.
        move.invoice_line_ids.sale_line_ids = [(5, 0, 0)]
        move.invoice_origin = 'B09999'
        self.assertFalse(move._liber_pedidos_da_nota(),
                         "o fixture precisa mesmo de uma nota sem pedido")

        tipo = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('warehouse_id', '=', self.wh.id)], limit=1)
        avulso = self.env['stock.picking'].create({
            'picking_type_id': tipo.id,
            'partner_id': self.partner.id,
            'origin': 'B09999',
            'company_id': self.company.id,
            'location_id': self.wh.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'location_id': self.wh.lot_stock_id.id,
                'location_dest_id': self.env.ref(
                    'stock.stock_location_customers').id,
                'company_id': self.company.id,
            })],
        })
        avulso.action_confirm()

        move._liber_danfe_para_pickings()

        self.assertEqual(avulso.nfe_move_id, move, "o mov achou a sua nota")
        self.assertTrue(avulso.has_nfe)
        self.assertTrue(self._anexos_do_picking(avulso),
                        "e a DANFE chegou ao chatter dele")
        self.assertFalse(so.picking_ids[0].nfe_move_id,
                         "sem carimbar o mov do pedido, que não é desta nota")

    def test_o_origin_nao_atropela_quem_tem_pedido(self):
        """A busca por origin é o PLANO B, e só roda quando o A volta vazio."""
        so, move = self._pedido_faturado()
        self._anexa_danfe(move)
        intruso = self.env['stock.picking'].create({
            'picking_type_id': self.env['stock.picking.type'].search([
                ('code', '=', 'outgoing'),
                ('warehouse_id', '=', self.wh.id)], limit=1).id,
            'partner_id': self.partner.id,
            'origin': so.name,
            'company_id': self.company.id,
        })

        move._liber_danfe_para_pickings()

        self.assertEqual(so.picking_ids[0].nfe_move_id, move)
        self.assertFalse(intruso.nfe_move_id,
                         "quem tem pedido não passa pela busca por origin")

    # ------------------------------------------------------------------
    # bordas: acerto (sem movimento) e PDF que não baixou
    # ------------------------------------------------------------------
    def test_nota_sem_pedido_nao_faz_nada(self):
        so, move = self._pedido_faturado()
        move.invoice_line_ids.sale_line_ids = [(5, 0, 0)]
        move.invoice_origin = False  # um acerto: nota sem movimento físico
        picking = so.picking_ids[0]

        move._liber_danfe_para_pickings()  # não pode quebrar

        self.assertFalse(picking.nfe_move_id)
        self.assertFalse(picking.has_nfe)

    def test_sem_pdf_vincula_mas_nao_posta(self):
        so, move = self._pedido_faturado()  # nenhum anexo criado
        picking = so.picking_ids[0]
        mensagens = len(picking.message_ids)

        move._liber_danfe_para_pickings()

        self.assertEqual(picking.nfe_move_id, move,
                         "o vínculo não espera o PDF")
        self.assertEqual(len(self._anexos_do_picking(picking)), 0)
        self.assertEqual(len(picking.message_ids), mensagens)

    # ------------------------------------------------------------------
    # cancelamento: avisa uma vez, e uma vez só
    # ------------------------------------------------------------------
    def test_cancelamento_avisa_no_chatter(self):
        so, move = self._pedido_faturado()
        self._anexa_danfe(move)
        move._liber_danfe_para_pickings()
        picking = so.picking_ids[0]
        mensagens = len(picking.message_ids)

        move.focus_status = 'cancelado'
        move._liber_avisar_cancelamento_nos_pickings()
        self.assertEqual(len(picking.message_ids), mensagens + 1)
        self.assertTrue(picking.nfe_cancel_notified)

        move._liber_avisar_cancelamento_nos_pickings()
        self.assertEqual(len(picking.message_ids), mensagens + 1,
                         "o aviso de cancelamento não se repete")

    # ------------------------------------------------------------------
    # erro: a propagação nunca derruba a emissão
    # ------------------------------------------------------------------
    def test_falha_na_propagacao_nao_derruba_o_gancho(self):
        so, move = self._pedido_faturado()
        with patch.object(am.AccountMove, '_liber_danfe_para_pickings',
                          side_effect=Exception('boom')):
            # resposta vazia: o super não baixa nada e não fala com a Focus
            move._focus_guardar_documentos({})
        # chegou aqui sem levantar: a emissão sobrevive à ponte quebrada

    def test_gancho_dispara_na_autorizacao(self):
        so, move = self._pedido_faturado()
        self._anexa_danfe(move)

        move._focus_guardar_documentos({})  # o que o cron chama, sem rede

        self.assertEqual(so.picking_ids[0].nfe_move_id, move)

    # ------------------------------------------------------------------
    # Imprimir > Notas fiscais
    # ------------------------------------------------------------------
    def _render_danfes(self, pickings):
        return self.env['ir.actions.report']._render_qweb_pdf(
            REPORT, res_ids=pickings.ids)

    def test_imprimir_uma_nota(self):
        so, move = self._pedido_faturado()
        self._anexa_danfe(move)
        move._liber_danfe_para_pickings()

        pdf, tipo = self._render_danfes(so.picking_ids[0])

        self.assertEqual(tipo, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_imprimir_duas_juntas_emenda_num_pdf(self):
        so1, move1 = self._pedido_faturado()
        so2, move2 = self._pedido_faturado()
        for move in (move1, move2):
            self._anexa_danfe(move)
            move._liber_danfe_para_pickings()
        pickings = so1.picking_ids[0] | so2.picking_ids[0]

        pdf, tipo = self._render_danfes(pickings)

        self.assertEqual(tipo, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'))
        # Emendado de verdade: maior que qualquer uma das partes sozinha.
        partes = [len(pdf_minimo('DANFE %s' % m.focus_ref))
                  for m in (move1, move2)]
        self.assertGreater(len(pdf), max(partes))

    def test_imprimir_sem_nota_barra_e_explica(self):
        so, _move = self._pedido_faturado()  # nota nunca propagada
        with self.assertRaises(UserError) as capto:
            self._render_danfes(so.picking_ids[0])
        self.assertIn(so.picking_ids[0].name, str(capto.exception))

    def test_logistica_imprime_sem_faturamento(self):
        """O perfil a quem tudo isto serve: só estoque, nenhum grupo contábil.

        É o Logística/Assistente do liber_roles (= stock.group_stock_user).
        Ele tem de ler os campos da ficha (related lê com sudo) e imprimir a
        DANFE — o sudo pontual do relatório existe para este teste passar.
        """
        so, move = self._pedido_faturado()
        self._anexa_danfe(move)
        move._liber_danfe_para_pickings()
        picking = so.picking_ids[0]

        deposito = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Depósito do Teste DANFE',
                'login': 'deposito.danfe',
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id])],
                'group_ids': [(4, self.env.ref('stock.group_stock_user').id)],
            })

        picking_dele = picking.with_user(deposito)
        self.assertEqual(picking_dele.nfe_numero, '4242')
        self.assertTrue(picking_dele.has_nfe)

        pdf, tipo = self.env['ir.actions.report'].with_user(
            deposito)._render_qweb_pdf(REPORT, res_ids=picking.ids)
        self.assertEqual(tipo, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_logistica_imprime_mov_sem_pedido(self):
        """O caso que faltava: imprimir a DANFE de uma remessa sem pedido.

        É o pedido dele em 31/08/2026 -- "era só o imprimir mesmo". A
        logística já imprimia a nota de uma venda; a da bonificação não, porque
        a nota nunca chegava ao mov (não há pedido entre os dois). Com o elo
        pelo nome da origem, o mesmo caminho serve aos dois -- e nenhum grupo
        contábil entra na conta.
        """
        so, move = self._pedido_faturado()
        self._anexa_danfe(move)
        move.invoice_line_ids.sale_line_ids = [(5, 0, 0)]
        move.invoice_origin = 'B08888'
        tipo = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('warehouse_id', '=', self.wh.id)], limit=1)
        avulso = self.env['stock.picking'].create({
            'picking_type_id': tipo.id,
            'partner_id': self.partner.id,
            'origin': 'B08888',
            'company_id': self.company.id,
        })
        move._liber_danfe_para_pickings()
        self.assertEqual(avulso.nfe_move_id, move)

        deposito = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Depósito do Mov Sem Pedido',
                'login': 'deposito.sem.pedido',
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id])],
                'group_ids': [(4, self.env.ref('stock.group_stock_user').id)],
            })
        dele = avulso.with_user(deposito)
        self.assertEqual(dele.nfe_numero, '4242')
        self.assertTrue(dele.has_nfe)

        pdf, formato = self.env['ir.actions.report'].with_user(
            deposito)._render_qweb_pdf(REPORT, res_ids=avulso.ids)
        self.assertEqual(formato, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_imprimir_mistura_barra_pela_que_falta(self):
        so1, move1 = self._pedido_faturado()
        self._anexa_danfe(move1)
        move1._liber_danfe_para_pickings()
        so2, _move2 = self._pedido_faturado()  # esta ficou sem nota

        with self.assertRaises(UserError) as capto:
            self._render_danfes(so1.picking_ids[0] | so2.picking_ids[0])
        self.assertIn(so2.picking_ids[0].name, str(capto.exception))
        self.assertNotIn(so1.picking_ids[0].name, str(capto.exception))

class TestVolumesEPeso(TransactionCase):
    """Nota que carrega caixa não sai sem dizer quantas e quanto pesa.

    O acerto de consignação passa direto: ele fatura livro que já está na
    prateleira do cliente e não move volume nenhum.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Journal = cls.env['account.journal'].sudo()
        cls.wh = None
        for wh in cls.env['stock.warehouse'].sudo().search([]):
            if Journal.search_count([('type', '=', 'sale'),
                                     ('company_id', '=', wh.company_id.id)]):
                cls.wh = wh
                break
        assert cls.wh, "nenhum armazém com diário de venda no banco de teste"
        cls.company = cls.wh.company_id
        cls.env = cls.env(context=dict(
            cls.env.context, allowed_company_ids=cls.company.ids))
        # A emissão exige operação fiscal; sem um padrão na empresa a nota
        # morre no CFOP antes de chegar aos volumes, que é o que se testa aqui.
        cls.company.write({
            'focus_operacao_padrao_id': operacao_de(cls.env, '102', 'saida').id})
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria dos Volumes', 'company_id': False})
        # `is_storable` não é enfeite no fixture: é o critério de "produto
        # contável" do aviso de volumes, e o livro de verdade da casa
        # rastreia estoque. Sem ele, o teste mediria um produto que não
        # existe na prateleira de ninguém.
        # Com peso na ficha: é assim que o cálculo tem de onde sair.
        cls.livro_pesado = cls.env['product.product'].create({
            'name': 'Livro Pesado', 'type': 'consu', 'is_storable': True,
            'invoice_policy': 'order', 'list_price': 50.0, 'weight': 0.4})
        # Sem peso: o caso real da casa hoje (nenhum livro tem peso no prod).
        cls.livro_sem_peso = cls.env['product.product'].create({
            'name': 'Livro Sem Peso', 'type': 'consu', 'is_storable': True,
            'invoice_policy': 'order', 'list_price': 50.0})

    def _pedido_faturado(self, produto, qty=3):
        so = self.env['sale.order'].with_company(self.company).create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'warehouse_id': self.wh.id,
            'order_line': [(0, 0, {'product_id': produto.id,
                                   'product_uom_qty': qty,
                                   'price_unit': 50.0})],
        })
        so.action_confirm()
        move = so._create_invoices()
        preparar_documento_latam(move)
        return so, move

    def test_puxa_caixas_e_peso_da_movimentacao(self):
        so, move = self._pedido_faturado(self.livro_pesado)
        so.picking_ids.box_count = 2
        move.action_liber_puxar_volumes()
        self.assertEqual(move.nfe_volumes, 2, "a caixa vem da contagem de quem embala")
        self.assertAlmostEqual(move.nfe_peso_bruto, 1.2, places=3,
                               msg="3 livros de 0,4 kg")

    def test_emissao_preenche_sozinha_quando_a_movimentacao_tem_os_dados(self):
        """Ninguém precisa clicar em nada quando o cadastro tem os dados."""
        so, move = self._pedido_faturado(self.livro_pesado)
        so.picking_ids.box_count = 1
        move._liber_conferir_volumes()
        self.assertEqual(move.nfe_volumes, 1)
        self.assertAlmostEqual(move.nfe_peso_bruto, 1.2, places=3)

    def test_sem_caixa_a_emissao_e_barrada(self):
        so, move = self._pedido_faturado(self.livro_pesado)
        move.action_post()
        with self.assertRaises(UserError) as erro:
            move._focus_build_payload()   # pelo caminho real da emissão
        self.assertIn('caixas', str(erro.exception))
        self.assertIn(so.picking_ids[0].name, str(erro.exception),
                      "a mensagem diz em qual transferência contar")

    def test_sem_peso_a_emissao_e_barrada(self):
        """Livro sem peso na ficha: o cálculo dá zero e a nota não sai."""
        so, move = self._pedido_faturado(self.livro_sem_peso)
        so.picking_ids.box_count = 1
        move.action_post()
        with self.assertRaises(UserError) as erro:
            move._focus_build_payload()
        self.assertIn('peso', str(erro.exception))

    def test_aviso_no_confirmar_recarrega_a_tela(self):
        """O aviso de volumes devolve o toast E o recarregamento da tela.

        Sem o ``next``, a devolução do toast SUBSTITUÍA o reload padrão do
        formulário: a fatura lançava no servidor, a tela seguia mostrando
        "Rascunho" e o segundo Confirmar levava "deve estar em rascunho"
        (visto na operação em 17/08/2026)."""
        so, move = self._pedido_faturado(self.livro_sem_peso)

        acao = move.action_post()

        self.assertEqual(move.state, 'posted',
                         "o aviso não bloqueia: a fatura confirma")
        self.assertEqual(acao['params']['next']['tag'], 'soft_reload',
                         "o toast precisa mandar a tela se recarregar, ou o "
                         "usuário confirma de novo uma fatura já lançada")

    def test_acerto_do_legado_nao_pede_caixa(self):
        """Pedido atrás da nota e nenhuma transferência de carga: sem aviso.

        É a forma dos acertos migrados do legado (milhares deles): a venda
        existe, a movimentação não -- ela aconteceu na vida real, anos atrás,
        fora deste banco. Cobrar caixa e peso dessa nota é cobrar por uma
        remessa que este Odoo nunca viu. A nota de mercadoria feita à mão,
        sem pedido nenhum, continua avisando."""
        so, move = self._pedido_faturado(self.livro_sem_peso)
        so.picking_ids.action_cancel()
        so.picking_ids.unlink()

        acao = move.action_post()

        self.assertEqual(move.state, 'posted')
        self.assertFalse(move._liber_volumes_faltando(),
                         "sem carga não há o que declarar nem o que avisar")
        self.assertNotEqual((acao or {}).get('tag'), 'display_notification',
                            "e portanto nenhum toast de volumes")

    def test_valor_digitado_pelo_faturista_vale(self):
        """Quem fatura pesa a caixa e digita: o valor dele não é sobrescrito."""
        so, move = self._pedido_faturado(self.livro_sem_peso)
        so.picking_ids.box_count = 9
        move.write({'nfe_volumes': 4, 'nfe_peso_bruto': 9.75})
        move._liber_conferir_volumes()
        self.assertEqual(move.nfe_volumes, 4,
                         "o número digitado ganha do contado na transferência")
        self.assertAlmostEqual(move.nfe_peso_bruto, 9.75, places=3)
        self.assertEqual(move.nfe_especie_volumes, 'CAIXA')

    def test_nota_sem_movimentacao_passa_sem_volumes(self):
        """Acerto (CO): sem transferência, sem exigência e sem grupo transp."""
        move = self.env['account.move'].with_company(self.company).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.livro_sem_peso.id,
                'quantity': 2, 'price_unit': 50.0})],
        })
        self.assertFalse(move._liber_pickings_da_nota(),
                         "o acerto não tem transferência, de propósito")
        move._liber_conferir_volumes()   # não pode barrar
        self.assertFalse(move.nfe_volumes)
        self.assertFalse(move.nfe_peso_bruto)


    # ------------------------------------------------------------------
    # A contagem da Logística chega à nota na CONFIRMAÇÃO (11/08/2026)
    # ------------------------------------------------------------------
    def test_confirmar_traz_a_contagem_da_logistica(self):
        """O pedido da direção: a caixa contada no depósito vai para a fatura.

        Antes, isso só acontecia na hora de emitir -- a fatura provisória
        mostrava zero e parecia que a integração não existia.
        """
        so, move = self._pedido_faturado(self.livro_pesado)
        so.picking_ids.box_count = 3
        self.assertFalse(move.nfe_volumes, "provisória ainda não sabe")

        move.action_post()

        self.assertEqual(move.nfe_volumes, 3,
                         "a confirmação não trouxe a contagem da transferência")
        self.assertAlmostEqual(move.nfe_peso_bruto, 1.2, places=3)

    def test_confirmar_avisa_sem_bloquear(self):
        """Avisar, não barrar: a fatura se confirma e o recado fica no chatter.

        As duas metades importam. Se bloquear, a casa para de faturar por
        causa de uma caixa que ainda não foi contada; se não avisar, o erro
        aparece só na emissão, longe de quem podia ter resolvido.
        """
        so, move = self._pedido_faturado(self.livro_sem_peso)
        antes = len(move.message_ids)

        move.action_post()   # não pode levantar nada

        self.assertEqual(move.state, 'posted', "o aviso bloqueou a confirmação")
        recados = move.message_ids[:len(move.message_ids) - antes]
        corpo = ' '.join(r.body or '' for r in recados)
        self.assertIn('caixas', corpo, "o chatter não recebeu o aviso")
        self.assertIn('peso', corpo)

    def test_nota_completa_confirma_calada(self):
        """O outro lado: nota que declara tudo não enche o chatter de recado."""
        so, move = self._pedido_faturado(self.livro_pesado)
        so.picking_ids.box_count = 2
        antes = len(move.message_ids)

        move.action_post()

        recados = move.message_ids[:len(move.message_ids) - antes]
        corpo = ' '.join(r.body or '' for r in recados)
        self.assertNotIn('ainda não declara', corpo,
                         "avisou numa nota que estava completa")

    def test_servico_nao_pede_caixa(self):
        """`is_storable` é o critério: serviço não ocupa caixa nem pesa."""
        servico = self.env['product.product'].create({
            'name': 'Assessoria de imprensa', 'type': 'service',
            'list_price': 500.0})
        move = self.env['account.move'].with_company(self.company).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': servico.id, 'quantity': 1,
                'price_unit': 500.0})],
        })
        preparar_documento_latam(move)
        self.assertFalse(move._liber_tem_produto_contavel())
        self.assertFalse(move._liber_volumes_faltando(),
                         "nota de serviço não deve pedir caixa nem peso")

    def test_nota_de_mercadoria_sem_movimentacao_tambem_avisa(self):
        """O critério novo é mais largo que o antigo, e de propósito.

        A nota feita à mão, com livro nela e sem transferência nenhuma, é
        justamente a que ninguém lembra de conferir. O `_liber_conferir_volumes`
        a deixa passar (não tem picking); o aviso da confirmação, não.
        """
        move = self.env['account.move'].with_company(self.company).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.livro_sem_peso.id,
                'quantity': 2, 'price_unit': 50.0})],
        })
        preparar_documento_latam(move)
        self.assertFalse(move._liber_pickings_da_nota())
        self.assertTrue(move._liber_volumes_faltando(),
                        "mercadoria sem movimentação também precisa de aviso")


class TestFreteETransportadora(TransactionCase):
    """Modalidade e transportadora nascem no cadastro e no pedido.

    A cascata da modalidade: pedido (negociada caso a caso), cadastro do
    cliente (padrão comercial), padrão da casa — CIF (decisão de
    12/08/2026). A transportadora vem do método de entrega da
    transferência, que o liber_transport herda do cadastro do cliente.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Journal = cls.env['account.journal'].sudo()
        cls.wh = None
        for wh in cls.env['stock.warehouse'].sudo().search([]):
            if Journal.search_count([('type', '=', 'sale'),
                                     ('company_id', '=', wh.company_id.id)]):
                cls.wh = wh
                break
        assert cls.wh, "nenhum armazém com diário de venda no banco de teste"
        cls.company = cls.wh.company_id
        cls.env = cls.env(context=dict(
            cls.env.context, allowed_company_ids=cls.company.ids))
        cls.company.write({
            'focus_operacao_padrao_id': operacao_de(cls.env, '102', 'saida').id})
        # O testing traz um ir.default global de carrier ("Entrega local");
        # sem removê-lo, o cliente-sem-transportadora não existiria aqui.
        cls.env['ir.default'].search([
            ('field_id.model', '=', 'res.partner'),
            ('field_id.name', '=', 'property_delivery_carrier_id'),
        ]).unlink()

        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria do Frete', 'company_id': False})
        cls.livro = cls.env['product.product'].create({
            'name': 'Livro com Peso', 'type': 'consu', 'is_storable': True,
            'invoice_policy': 'order', 'list_price': 50.0, 'weight': 0.4})

        cls.transportadora = cls.env['res.partner'].create({
            'name': 'Transportes Andorinha', 'is_company': True,
            'vat': '11222333000181'})
        frete_produto = cls.env['product.product'].create({
            'name': 'Frete Teste', 'type': 'service', 'sale_ok': False})
        cls.carrier = cls.env['delivery.carrier'].create({
            'name': 'Andorinha', 'delivery_type': 'fixed',
            'product_id': frete_produto.id,
            'partner_id': cls.transportadora.id})

    def _pedido_faturado(self, box_count=1):
        so = self.env['sale.order'].with_company(self.company).create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'warehouse_id': self.wh.id,
            'order_line': [(0, 0, {'product_id': self.livro.id,
                                   'product_uom_qty': 2,
                                   'price_unit': 50.0})],
        })
        so.action_confirm()
        so.picking_ids.box_count = box_count
        move = so._create_invoices()
        preparar_documento_latam(move)
        return so, move

    def test_pedido_herda_a_modalidade_do_cadastro(self):
        self.partner.nfe_modalidade_frete = '1'
        so, _move = self._pedido_faturado()
        self.assertEqual(so.nfe_modalidade_frete, '1',
                         "o padrão do cliente não desceu ao pedido")

    def test_confirmar_traz_cif_e_a_transportadora_do_cliente(self):
        """Nada escolhido em lugar nenhum: CIF, e o carrier do cadastro."""
        self.partner.with_company(self.company) \
            .property_delivery_carrier_id = self.carrier
        _so, move = self._pedido_faturado()
        move.action_post()

        self.assertEqual(move.nfe_modalidade_frete, '0',
                         "o padrão da casa é CIF")
        self.assertEqual(move.nfe_transportadora_id, self.transportadora,
                         "a transportadora não veio da transferência")

    def test_modalidade_negociada_no_pedido_ganha_do_cadastro(self):
        self.partner.nfe_modalidade_frete = '1'
        so, move = self._pedido_faturado()
        so.nfe_modalidade_frete = '2'
        move.action_post()

        self.assertEqual(move.nfe_modalidade_frete, '2',
                         "a negociação do pedido perde para o cadastro")

    def test_valor_digitado_na_fatura_vale(self):
        """Quem fatura é a última palavra, como nos volumes."""
        _so, move = self._pedido_faturado()
        move.nfe_modalidade_frete = '4'
        move.action_post()

        self.assertEqual(move.nfe_modalidade_frete, '4')

    def test_trocar_de_cliente_nao_apaga_a_negociacao(self):
        so, _move = self._pedido_faturado()
        so.nfe_modalidade_frete = '2'
        outro = self.env['res.partner'].create({
            'name': 'Banca Sem Padrão', 'company_id': False})
        so.partner_id = outro
        self.assertEqual(so.nfe_modalidade_frete, '2',
                         "trocar o cliente apagou a modalidade negociada")

    def test_acerto_fica_sem_frete(self):
        """Nota sem movimentação (o acerto) não ganha modalidade nem
        transportadora: o payload emite 9 — sem ocorrência de transporte."""
        move = self.env['account.move'].with_company(self.company).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.livro.id,
                'quantity': 2, 'price_unit': 50.0})],
        })
        preparar_documento_latam(move)
        move.action_post()

        self.assertFalse(move.nfe_modalidade_frete,
                         "o acerto não declara transporte")
        self.assertFalse(move.nfe_transportadora_id)
