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

    def _wire_fiscal(self):
        mirror = self.env["account.account"].search(
            [("code", "=", "CONTST")], limit=1) or \
            self.env["account.account"].create({
                "code": "CONTST",
                "name": "(-) Remessa de Consignação (fixture)",
                "account_type": "income_other",
                "company_ids": [(4, self.company.id)]})
        fpos = self.env["account.fiscal.position"].search(
            [("name", "=", "Consignação — Remessa (fixture)"),
             ("company_id", "=", self.company.id)], limit=1) or \
            self.env["account.fiscal.position"].create({
                "name": "Consignação — Remessa (fixture)",
                "company_id": self.company.id,
                "auto_invoice_paid": True,
                "auto_invoice_paid_account_id": mirror.id})
        self.company.consignment_shipment_fiscal_position_id = fpos
        return fpos

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
        self.assertTrue(picking.name.startswith("COM/"),
                        "got %r, wanted COM/*" % picking.name)

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
        order = self._pedido_c()
        order.action_confirm()
        order.action_generate_remessa_note()
        note = order.remessa_note_move_id
        self.assertTrue(note, "no note was generated")
        self.assertEqual(note.move_type, 'out_invoice')
        self.assertTrue(note.name.startswith("REM/"),
                        "got %r, wanted the REM/ sequence" % note.name)
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
