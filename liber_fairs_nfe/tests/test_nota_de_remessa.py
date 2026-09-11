# -*- coding: utf-8 -*-
"""A nota de simples remessa da feira.

Três regras, e nenhuma delas é detalhe:

1. o destinatário é a PRÓPRIA EMPRESA. A mercadoria não muda de dono ao subir
   na van, muda de lugar;
2. a nota declara o que REALMENTE saiu, e não o que foi planejado. Uma nota
   que diz 100 quando saíram 62 não bate com o volume na estrada;
3. uma carga, uma nota. Apertar o botão de novo não declara outra vez o que
   já viajou -- e numa feira com reposição isso emitiria a remessa inteira em
   dobro.
"""
from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs_nfe')
class TestNotaDeRemessa(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.livro = cls.env['product.product'].create({
            'name': 'Título com Nota', 'type': 'consu', 'is_storable': True,
            'list_price': 80.0})
        cls.env['stock.quant']._update_available_quantity(
            cls.livro, cls.warehouse.lot_stock_id, 100)
        cls.receita = cls.env['account.account'].search(
            [('account_type', '=', 'income'),
             ('company_ids', 'in', cls.company.id)], limit=1)
        cls.destino = cls.env['account.account'].search(
            [('account_type', '=', 'asset_current'),
             ('company_ids', 'in', cls.company.id)], limit=1)
        if not (cls.receita and cls.destino):
            cls.skipTest(cls, "banco sem plano de contas para a nota")
        cls.fpos = cls.env['account.fiscal.position'].create({
            'name': '(Z) Remessa para exposição ou feira',
            'company_id': cls.company.id,
            'auto_invoice_paid': True,
            'auto_invoice_paid_account_id': cls.destino.id,
            'account_ids': [(0, 0, {
                'account_src_id': cls.receita.id,
                'account_dest_id': cls.destino.id,
            })],
        })
        cls.company.fair_shipment_fiscal_position_id = cls.fpos
        cls.fpos_retorno = cls.env['account.fiscal.position'].create({
            'name': '(Z) Retorno de exposição ou feira',
            'company_id': cls.company.id,
            'auto_invoice_paid': True,
            'auto_invoice_paid_account_id': cls.destino.id,
            'account_ids': [(0, 0, {
                'account_src_id': cls.receita.id,
                'account_dest_id': cls.destino.id,
            })],
        })

    def _fair(self, qty=10):
        return self.env['event.fair'].create({
            'name': 'Feira com Nota',
            'date_start': date(2026, 9, 20),
            'date_end': date(2026, 9, 20) + timedelta(days=1),
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': qty})],
        })

    def _receber(self, fair):
        """Confere na praça o que estava a caminho: a segunda perna da ida."""
        for picking in fair.picking_ids.filtered(
                lambda p: p.fair_operation == 'receipt'
                and p.state not in ('done', 'cancel')):
            picking.action_assign()
            # NÃO se força a quantidade: recebe-se o que o trânsito tem de
            # verdade. Forçar aqui faria o teste receber nove exemplares de
            # um título que saiu zero do armazém -- exatamente a mentira que
            # a segunda perna existe para impedir.
            picking.move_ids.picked = True
            picking.with_context(
                skip_backorder=True,
                picking_ids_not_to_backorder=picking.ids).button_validate()
        return True

    def _despachar(self, fair, quantidade=None):
        picking = fair.action_ship()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = (move.product_uom_qty if quantidade is None
                             else quantidade)
            move.picked = True
        # Validar parcial abre o assistente de pedido pendente e não conclui
        # nada. Aqui não queremos backorder: o que saiu, saiu.
        picking.with_context(
            skip_backorder=True,
            picking_ids_not_to_backorder=picking.ids).button_validate()
        self._receber(fair)
        return picking

    # --- caminho feliz ----------------------------------------------------
    def test_the_note_is_issued_to_ourselves(self):
        fair = self._fair(10)
        fair.action_plan()
        self._despachar(fair)
        note = fair.action_generate_remessa_note()
        self.assertEqual(len(note), 1)
        self.assertEqual(note.partner_id, self.company.partner_id,
                         "A remessa para feira sai para nós mesmos")
        self.assertEqual(note.remessa_origin, 'event')
        self.assertEqual(note.fair_id, fair)
        self.assertEqual(note.state, 'posted')
        self.assertTrue(note.journal_id.is_remessa)
        self.assertEqual(note.journal_id.remessa_kind, 'event')

    def test_the_note_never_bills_anyone(self):
        """Nasce baixada: a editora não pode ficar devendo a si mesma."""
        fair = self._fair(10)
        fair.action_plan()
        self._despachar(fair)
        note = fair.action_generate_remessa_note()
        self.assertTrue(note.remessa_settle_move_id,
                        "A nota de remessa tem de nascer com a baixa")
        self.assertIn(note.payment_state, ('paid', 'in_payment', 'reversed'),
                      "Nota de remessa em aberto cobraria a própria casa")

    def test_the_note_declares_what_actually_left(self):
        """Planejado 10, despachado 6: a nota diz 6."""
        fair = self._fair(10)
        fair.action_plan()
        self._despachar(fair, quantidade=6)
        note = fair.action_generate_remessa_note()
        linha = note.invoice_line_ids.filtered(
            lambda l: l.product_id == self.livro)
        self.assertEqual(linha.quantity, 6,
                         "A nota que diz 10 com 6 na van não bate com a carga")

    def test_replenishment_gets_its_own_note(self):
        """Uma carga, uma nota: a reposição viaja com a dela."""
        fair = self._fair(10)
        fair.action_plan()
        self._despachar(fair)
        primeira = fair.action_generate_remessa_note()
        fair.line_ids.qty_planned = 16
        self._despachar(fair)
        segunda = fair.action_generate_remessa_note()
        self.assertNotEqual(primeira, segunda)
        self.assertEqual(fair.note_count, 2)
        soma = sum(segunda.invoice_line_ids.mapped('quantity'))
        self.assertEqual(soma, 6,
                         "A nota da reposição declara só a reposição")

    def test_pressing_twice_does_not_declare_the_same_load_again(self):
        fair = self._fair(10)
        fair.action_plan()
        self._despachar(fair)
        fair.action_generate_remessa_note()
        with self.assertRaises(UserError):
            fair.action_generate_remessa_note()
        self.assertEqual(fair.note_count, 1)

    # --- erro -------------------------------------------------------------
    def test_a_fair_that_has_not_shipped_has_nothing_to_declare(self):
        fair = self._fair(10)
        fair.action_plan()
        fair.action_ship()
        with self.assertRaises(UserError):
            fair.action_generate_remessa_note()

    def test_an_unconfigured_fiscal_position_says_what_is_missing(self):
        self.company.fair_shipment_fiscal_position_id = False
        fair = self._fair(10)
        fair.action_plan()
        self._despachar(fair)
        with self.assertRaises(UserError):
            fair.action_generate_remessa_note()

    def test_the_transfer_knows_its_note(self):
        """A logística vive na tela do movimento, e é lá que a nota tem de aparecer.

        Sem este carimbo a caixa fica pronta para viajar e o Imprimir diz
        "Sem nota fiscal" sobre uma carga cuja nota existe e está lançada: o
        `liber_nfe_picking` acha a nota andando pelo pedido de venda, e feira
        não tem pedido de venda.
        """
        picking_field = 'nfe_move_id' in self.env['stock.picking']._fields
        if not picking_field:
            self.skipTest("liber_nfe_picking não está instalado neste banco")
        fair = self._fair(10)
        fair.action_plan()
        picking = self._despachar(fair)
        self.assertFalse(picking.nfe_move_id)
        note = fair.action_generate_remessa_note()
        self.assertEqual(picking.nfe_move_id, note,
                         "A transferência tem de conhecer a sua nota")
        self.assertTrue(picking.has_nfe,
                        "O filtro Com nota fiscal precisa achar esta carga")

    # --- a nota da volta --------------------------------------------------
    def test_the_return_releases_its_note_in_the_same_click(self):
        """A carga não roda sem documento.

        A nota da volta viaja COM as caixas, então ela sai quando elas deixam
        a feira -- e não quando chegam. Por isso ela declara a quantidade
        PEDIDA, ao contrário da nota de ida, que sai depois de o armazém
        separar e por isso declara a despachada.
        """
        self.company.fair_return_fiscal_position_id = self.fpos_retorno
        fair = self._fair(10)
        fair.action_plan()
        self._despachar(fair)
        fair.action_generate_remessa_note()
        retorno = fair.action_return()
        self.assertEqual(retorno.fair_operation, 'return_dispatch')
        self.assertEqual(retorno.state, 'done',
                         "O clique em Retorno já tira a carga da mesa")
        nota = retorno.fair_note_move_id
        self.assertTrue(nota, "Retornar tem de liberar a nota na hora")
        self.assertEqual(nota.move_type, 'out_refund',
                         "Ida e volta se anulam: a volta é nota de crédito")
        self.assertEqual(nota.partner_id, self.company.partner_id)
        self.assertEqual(nota.fiscal_position_id, self.fpos_retorno)
        self.assertEqual(nota.state, 'posted')
        self.assertEqual(
            sum(nota.invoice_line_ids.mapped('quantity')), 10,
            "Declara o que está voltando")
        self.assertTrue(nota.remessa_settle_move_id,
                        "Também nasce baixada: ninguém deve nada")

    def test_the_return_note_points_at_the_outbound_one(self):
        self.company.fair_return_fiscal_position_id = self.fpos_retorno
        fair = self._fair(10)
        fair.action_plan()
        self._despachar(fair)
        ida = fair.action_generate_remessa_note()
        fair.action_return()
        volta = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'return_dispatch').fair_note_move_id
        if 'focus_nota_referenciada_id' in self.env['account.move']._fields:
            self.assertEqual(volta.focus_nota_referenciada_id, ida,
                             "A volta referencia a chave da ida")

    def test_accounting_does_not_block_the_warehouse(self):
        """Sem posição fiscal de retorno, a carga volta assim mesmo.

        Deixar as caixas na praça esperando alguém preencher um campo em
        Definições seria trocar um problema de cadastro por um problema de
        logística. O retorno acontece, e a feira registra em alto e bom som o
        que falta configurar -- a nota se emite depois, pelo botão.
        """
        self.company.fair_return_fiscal_position_id = False
        fair = self._fair(10)
        fair.action_plan()
        self._despachar(fair)
        antes = len(fair.message_ids)
        retorno = fair.action_return()
        self.assertTrue(retorno, "O retorno tem de acontecer")
        self.assertEqual(fair.state, 'returned')
        self.assertFalse(retorno.fair_note_move_id)
        self.assertGreater(len(fair.message_ids), antes,
                           "E a feira tem de dizer que saiu sem nota")
        self.assertIn('without a fiscal note', fair.message_ids[0].body)
        # configurado depois, o mesmo botão fecha a ponta que faltava
        self.company.fair_return_fiscal_position_id = self.fpos_retorno
        fair.action_generate_remessa_note()
        self.assertTrue(retorno.fair_note_move_id,
                        "O botão emite a nota que faltou")
        self.assertEqual(retorno.fair_note_move_id.move_type, 'out_refund')

    def test_the_fair_says_which_note_came_out(self):
        """A nota sai sozinha; a tela tem de contar que saiu.

        Sem isso o número aparece num contador no alto e mais nada, e quem
        acabou de apertar Retorno fica procurando onde emitir uma nota que
        já existe.
        """
        self.company.fair_return_fiscal_position_id = self.fpos_retorno
        fair = self._fair(10)
        fair.action_plan()
        self._despachar(fair)
        antes = len(fair.message_ids)
        ida = fair.action_generate_remessa_note()
        self.assertGreater(len(fair.message_ids), antes)
        self.assertIn(ida.name, fair.message_ids[0].body,
                      "O histórico tem de citar a nota de ida")
        fair.action_return()
        volta = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'return_dispatch').fair_note_move_id
        self.assertIn(volta.name, fair.message_ids[0].body,
                      "E a de volta, no clique do Retorno")
        self.assertIn('Remessas', fair.message_ids[0].body,
                      "dizendo onde ela mora")

    def test_the_note_button_shows_from_the_dispatch(self):
        """Escondido até o armazém validar, o botão some justo quando se procura.

        Quem acabou de apertar Despachar vai atrás da nota. A resposta certa
        -- "espere o armazém validar, a nota declara o que entrou na van" --
        é o que a tela tem de dizer, e para dizer ela precisa do botão ali.
        """
        fair = self._fair(10)
        fair.action_plan()
        picking = fair.action_ship()
        self.assertNotEqual(picking.state, 'done')
        self.assertTrue(fair.pickings_without_note,
                        "O botão tem de aparecer desde o despacho")
        with self.assertRaises(UserError):
            fair.action_generate_remessa_note()
        # validada a carga, o mesmo botão emite
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.with_context(
            skip_backorder=True,
            picking_ids_not_to_backorder=picking.ids).button_validate()
        nota = fair.action_generate_remessa_note()
        self.assertTrue(nota)
        self.assertFalse(fair.pickings_without_note,
                         "e some quando não falta mais nota nenhuma")
