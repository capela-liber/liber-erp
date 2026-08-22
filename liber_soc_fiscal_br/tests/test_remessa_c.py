# -*- coding: utf-8 -*-
"""The C000's fiscal note: also a remessa (18/07).

A Pedido C never invoices -- the books are still ours. Its note is a REM/
document under the CONSIGNMENT fiscal position from Settings: the field that
sat declared-but-unread since soc_fiscal_br shipped finally has its consumer,
and these tests are what keep it consumed.
"""
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_fiscal")
class TestRemessaC(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1)
        cls.product = cls.env["product.product"].create({
            "name": "Dom Casmurro", "type": "consu",
            "is_storable": True, "list_price": 45.0})
        cls.partner = cls.env["res.partner"].create({
            "name": "Livraria da Remessa", "is_company": True})
        agreement = cls.env["consignment.agreement"].create({
            "partner_id": cls.partner.id,
            "company_id": cls.company.id,
            "date_start": fields.Date.today(),
        })
        agreement.action_activate()

    def _conta(self, code, name, account_type="income_other"):
        Account = self.env["account.account"]
        return Account.search([("code", "=", code)], limit=1) or Account.create({
            "code": code, "name": name, "account_type": account_type,
            "company_ids": [(4, self.company.id)]})

    def _wire_fiscal(self, com_mapa=True):
        """The consignment operation, configured as production has it.

        Two halves, and the fixture used to carry only one. The auto-paid pair
        settles the receivable; the ACCOUNT MAP is what moves the value out of
        revenue -- "conta de receita X vira a conta da operação Y". Without the
        map the fixture was greener than the house, and that is how a note
        with no account at all reached staging.
        """
        mirror = self._conta("CONTST", "(-) Remessa de Consignação (fixture)",
                             account_type="asset_current")
        self.destino = self._conta(
            "CONDST", "(+) Investimento em Consignação (fixture)",
            account_type="asset_current")
        fpos = self.env["account.fiscal.position"].search(
            [("name", "=", "Consignação — Remessa (fixture)"),
             ("company_id", "=", self.company.id)], limit=1) or \
            self.env["account.fiscal.position"].create({
                "name": "Consignação — Remessa (fixture)",
                "company_id": self.company.id,
                "auto_invoice_paid": True,
                "auto_invoice_paid_account_id": mirror.id})
        fpos.account_ids.unlink()
        if com_mapa:
            self.env["account.fiscal.position.account"].create({
                "position_id": fpos.id,
                "account_src_id": self._conta_receita_do_produto().id,
                "account_dest_id": self.destino.id,
            })
        self.company.consignment_shipment_fiscal_position_id = fpos
        return fpos

    def _conta_receita_do_produto(self):
        return self.product.product_tmpl_id.get_product_accounts()["income"]

    def _catalogo_da_casa(self):
        """The real catalogue: no account on the product, none on the category.

        6.137 products and 243 categories in production, not one with an
        income account -- the house has always let the journal carry it. It is
        the case the fixture never had, and the only one where the journal's
        account is reached at all.
        """
        self.product.product_tmpl_id.property_account_income_id = False
        self.product.categ_id.property_account_income_categ_id = False

    def _pedido_c(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "is_consignment": True,
            "consignment_type": "opening",
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 6,
                "price_unit": 45.0})],
        })
        return order

    def _pedido_c_expedido(self, qty=6):
        """Pedido C com a mercadoria fora do armazém -- a nota exige isso.

        Os fixtures antigos geravam nota sem expedir nada, e por isso a suíte
        inteira passava enquanto o C08547 saía com 100 livros que nunca
        deixaram a estante.
        """
        self._estoque(qty + 10)
        order = self._pedido_c()
        order.action_confirm()
        self._expedir(order, qty)
        return order

    def test_delivery_ships_on_the_consignment_operation_type(self):
        """"Uma remessa de consignação deveria ter um tipo de operação e um
        prefixo diferente." C00003 came out WH/OUT; never again."""
        order = self._pedido_c()
        order.action_confirm()
        picking = order.picking_ids
        self.assertTrue(picking, "the Pedido C spawned no delivery")
        self.assertEqual(picking.picking_type_id.code, 'outgoing')
        self.assertEqual(
            picking.picking_type_id,
            self.company.consignment_delivery_operation_type_id,
            "the delivery must ride the consignment operation type, "
            "not the warehouse's generic %s" % picking.picking_type_id.name)
        self.assertTrue(picking.name.startswith("COM/OUT/"),
                        "got %r, wanted COM/OUT/*" % picking.name)

    def test_ordinary_sale_keeps_its_generic_delivery(self):
        """The rule must not leak onto real sales."""
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 1, "price_unit": 45.0})],
        })
        order.action_confirm()
        self.assertFalse(order.picking_ids.name.startswith("COM/"),
                         "a real sale rode the consignment type: %s"
                         % order.picking_ids.name)

    def test_c000_note_is_a_remessa_never_billed(self):
        """The C000's note: REM/ document, consignment position, nothing owed.

        The bookseller holds books that are still OURS; a note that billed
        them would charge for goods nobody bought. The auto-paid pair on the
        consignment fiscal position is what makes that impossible.
        """
        fpos = self._wire_fiscal()
        order = self._pedido_c_expedido()
        order.action_generate_remessa_note()
        note = order.remessa_note_move_id
        self.assertTrue(note, "no note was generated")
        self.assertEqual(note.move_type, 'out_invoice')
        self.assertTrue(note.name.startswith("REM-C/"),
                        "got %r, wanted the REM-C/ sequence" % note.name)
        self.assertEqual(note.fiscal_position_id, fpos,
                         "the CONSIGNMENT position from Settings -- the dead "
                         "field, alive")
        self.assertEqual(note.payment_state, 'paid')
        self.assertEqual(note.amount_residual, 0.0,
                         "the bookseller must never owe for consigned books")
        self.assertEqual(note.remessa_origin, 'consignment',
                         "Remessas must be able to tell a C note from a B note")
        # idempotent: generating again does not duplicate
        order.action_generate_remessa_note()
        self.assertEqual(order.remessa_note_move_id, note)

    def test_note_refuses_without_the_fiscal_mapping(self):
        """Half-configured must refuse loudly, not bill quietly."""
        self.company.consignment_shipment_fiscal_position_id = False
        order = self._pedido_c()
        order.action_confirm()
        with self.assertRaises(UserError) as e:
            order.action_generate_remessa_note()
        self.assertIn("5917", str(e.exception),
                      "the error must name the consignment remessa CFOP")

    def test_note_only_for_pedido_c(self):
        """A real sale invoices through Criar fatura, not here."""
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 1, "price_unit": 45.0})],
        })
        with self.assertRaises(UserError):
            order.action_generate_remessa_note()

    # --- a conta da nota: onde a remessa cai ------------------------------
    def test_a_nota_do_catalogo_da_casa_cai_na_conta_da_operacao(self):
        """The bug staging found: a note with no account on the line.

        Product without account, category without account, journal without
        account -- the three steps Odoo walks, all empty, and Postgres refuses
        the line ("Conta necessária ausente na linha contábil"). The journal
        is the last step, and it is now born carrying the account the fiscal
        position declares.
        """
        fpos = self._wire_fiscal()
        self._catalogo_da_casa()
        order = self._pedido_c_expedido()
        order.action_generate_remessa_note()
        note = order.remessa_note_move_id
        linhas = note.line_ids.filtered(lambda l: l.display_type == 'product')
        self.assertTrue(linhas, "the note has no product line")
        self.assertEqual(linhas.account_id, self.destino,
                         "the remessa must land on the operation's account")
        self.assertEqual(note.journal_id.remessa_kind, 'consignment')
        self.assertEqual(note.journal_id.default_account_id, self.destino,
                         "the journal is born carrying the mapped account")

    def test_a_remessa_nunca_toca_receita(self):
        """A remessa is value without a sale: revenue must stay untouched.

        This is the check that would have caught the first fix I tried on
        staging -- copying the sales journal's account made the note come out,
        and booked R$ 799 of revenue for books nobody bought.
        """
        self._wire_fiscal()
        self._catalogo_da_casa()
        order = self._pedido_c_expedido()
        order.action_generate_remessa_note()
        note = order.remessa_note_move_id
        contas = note.line_ids.account_id + \
            note.remessa_settle_move_id.line_ids.account_id
        receitas = contas.filtered(lambda a: a.account_type.startswith('income'))
        self.assertFalse(receitas,
                         "a remessa booked revenue: %s" % receitas.mapped('code'))

    def test_sem_mapa_de_contas_o_erro_diz_o_que_falta(self):
        """Half-configured refuses loudly: it must name the missing map."""
        self._wire_fiscal(com_mapa=False)
        self._catalogo_da_casa()
        order = self._pedido_c_expedido()
        with self.assertRaises(UserError) as e:
            order.action_generate_remessa_note()
        self.assertIn("revenue account", str(e.exception),
                      "the error must say which mapping is missing")

    def test_divergencia_entre_diario_e_posicao_fiscal_aparece(self):
        """The journal carries a photograph of the map. Photographs age.

        Change the map afterwards and the journal keeps booking to the old
        account -- silently, which is the worst way to be wrong about money.
        This is the check that makes the disagreement visible.
        """
        fpos = self._wire_fiscal()
        self._catalogo_da_casa()
        order = self._pedido_c_expedido()
        order.action_generate_remessa_note()
        self.assertFalse(self.company._remessa_journals_out_of_sync(),
                         "fresh journal and map must agree")
        outra = self._conta("CONDST2", "(+) Outra conta (fixture)",
                            account_type="asset_current")
        fpos.account_ids.account_dest_id = outra
        divergentes = self.company._remessa_journals_out_of_sync()
        self.assertEqual(len(divergentes), 1, "the drift went unnoticed")
        journal, esperada = divergentes[0]
        self.assertEqual(journal.remessa_kind, 'consignment')
        self.assertEqual(esperada, outra)

    # --- a nota declara o que saiu, não o que foi pedido ------------------
    def _estoque(self, qty):
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": self.product.id,
            "location_id": self.warehouse.lot_stock_id.id,
            "inventory_quantity": qty,
        }).action_apply_inventory()

    def _expedir(self, order, qty):
        """Valida a transferência do pedido com a quantidade que couber."""
        picking = order.picking_ids.filtered(lambda p: p.state != 'cancel')
        for move in picking.move_ids:
            move.quantity = qty
            move.picked = True
        picking.with_context(skip_backorder=True,
                             picked_off_backorder=True).button_validate()
        return picking

    def test_a_nota_recusa_enquanto_a_mercadoria_nao_saiu(self):
        """C08547: pedido de 100, estoque para 62, nada expedido, nota de 100.

        A nota de remessa viaja com a carga. Declarar livro que ainda está na
        estante é o que a fiscalização pega na estrada -- e o erro tem que
        dizer qual transferência falta validar.
        """
        self._wire_fiscal()
        self._catalogo_da_casa()
        self._estoque(50)
        order = self._pedido_c()
        order.action_confirm()
        with self.assertRaises(UserError) as e:
            order.action_generate_remessa_note()
        msg = str(e.exception)
        self.assertIn("não movimentou mercadoria", msg)
        self.assertIn(order.picking_ids[:1].name, msg,
                      "o erro tem que nomear a transferência a validar")
        self.assertFalse(order.remessa_note_move_id, "nasceu nota mesmo assim")

    def test_a_nota_leva_a_quantidade_expedida_e_nao_a_pedida(self):
        """Saiu menos do que foi pedido: a nota diz o que saiu."""
        self._wire_fiscal()
        self._catalogo_da_casa()
        self._estoque(50)
        order = self._pedido_c()          # pede 6
        order.action_confirm()
        self._expedir(order, 4)           # saem 4
        order.action_generate_remessa_note()
        linha = order.remessa_note_move_id.invoice_line_ids
        self.assertEqual(linha.quantity, 4,
                         "a nota saiu com o pedido, não com a carga")
        self.assertEqual(order.order_line.product_uom_qty, 6,
                         "o pedido não pode ser reescrito pela nota")

    def test_expedicao_completa_leva_tudo(self):
        """O caminho feliz continua inteiro."""
        self._wire_fiscal()
        self._catalogo_da_casa()
        self._estoque(50)
        order = self._pedido_c()
        order.action_confirm()
        self._expedir(order, 6)
        order.action_generate_remessa_note()
        self.assertEqual(order.remessa_note_move_id.invoice_line_ids.quantity, 6)


    # --- nota cancelada não prende o pedido -------------------------------
    def test_nota_cancelada_libera_o_pedido_para_emitir_de_novo(self):
        """21/08: uma NF-e cancelada na SEFAZ deixou o C000 preso.

        O botão só olhava se EXISTIA nota, não se ela ainda era um documento.
        Cancelada a nota, o pedido ficava sem documento fiscal e sem botão --
        e a saída foi mexer no banco à mão. Cancelada a nota, o C000 volta a
        poder emitir; nota viva continua segurando.
        """
        self._wire_fiscal()
        self._catalogo_da_casa()
        order = self._pedido_c_expedido()
        order.action_generate_remessa_note()
        primeira = order.remessa_note_move_id
        self.assertEqual(order.remessa_note_label, primeira.name)

        primeira.button_draft()
        primeira.button_cancel()
        self.assertEqual(order.remessa_note_label, "A emitir",
                         "o botão inteligente continuou anunciando nota morta")

        order.action_generate_remessa_note()
        segunda = order.remessa_note_move_id
        self.assertNotEqual(segunda, primeira, "o pedido continuou preso")
        self.assertEqual(segunda.state, 'posted')
        self.assertEqual(segunda.invoice_line_ids.quantity, 6,
                         "a nota nova tem que declarar a mesma carga")

    def test_nota_viva_continua_segurando_o_pedido(self):
        """A idempotência não pode ir junto: apertar duas vezes não duplica."""
        self._wire_fiscal()
        self._catalogo_da_casa()
        order = self._pedido_c_expedido()
        order.action_generate_remessa_note()
        nota = order.remessa_note_move_id
        order.action_generate_remessa_note()
        self.assertEqual(order.remessa_note_move_id, nota)
