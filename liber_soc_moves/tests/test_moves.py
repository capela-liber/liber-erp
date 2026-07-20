# -*- coding: utf-8 -*-
"""Tests for consignment moves: the COM/RET flows get their own pickings
(never WH/OUT), and the Pedido C never reaches invoicing."""
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_moves")
class TestConsignmentMoves(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1)
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.product = cls.env["product.product"].create({
            "name": "Memórias Póstumas", "type": "consu",
            "is_storable": True, "list_price": 50.0})
        partner = cls.env["res.partner"].create({
            "name": "Livraria Consignada", "is_company": True})
        cls.agreement = cls.env["consignment.agreement"].create({
            "partner_id": partner.id,
            "company_id": cls.company.id,
            "date_start": fields.Date.today(),
        })
        cls.agreement.action_activate()
        cls.partner = partner

    def _move(self, kind, qty=10):
        return self.env["consignment.move"].create({
            "partner_id": self.partner.id,
            "move_kind": kind,
            "line_ids": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": qty,
            })],
        })

    def test_shipment_uses_rem_picking_to_shelf(self):
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.stock_loc, 20)
        move = self._move("shipment")
        move.action_confirm()
        self.assertEqual(move.state, "waiting",
                         "a physical move waits before touching stock")
        move.action_release()
        self.assertEqual(move.state, "confirmed")
        picking = move.picking_id
        self.assertTrue(picking)
        # COM/ desde 18/07: REM/ passou ao documento fiscal (nfe_remessa)
        self.assertTrue(picking.name.startswith("COM/"),
                        "shipment picking got %r, wanted COM/*" % picking.name)
        self.assertEqual(picking.location_id, self.stock_loc)
        self.assertEqual(picking.location_dest_id, self.agreement.location_id)
        # validate: stock lands on the shelf
        picking.button_validate()
        self.assertEqual(self.agreement.on_shelf_qty, 10)

    def test_return_uses_ret_picking_from_shelf(self):
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.agreement.location_id, 10)
        move = self._move("return", qty=4)
        move.action_confirm()
        move.action_release()
        picking = move.picking_id
        self.assertTrue(picking.name.startswith("RET/"),
                        "return picking got %r, wanted RET/*" % picking.name)
        self.assertEqual(picking.location_id, self.agreement.location_id)
        self.assertEqual(picking.location_dest_id, self.stock_loc)

    def test_confirm_guards(self):
        # no lines
        empty = self.env["consignment.move"].create({
            "partner_id": self.partner.id, "move_kind": "shipment"})
        with self.assertRaises(UserError):
            empty.action_confirm()
        # inactive agreement
        self.agreement.write({"state": "suspended"})
        move = self._move("shipment")
        with self.assertRaises(UserError):
            move.action_confirm()
        self.agreement.write({"state": "active"})

    def test_symbolic_renewal_completes_without_picking(self):
        move = self._move("symbolic_renewal", qty=1)
        move.action_confirm()
        self.assertEqual(move.state, "done")
        self.assertFalse(move.picking_id)

    def test_pedido_c_never_invoices(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "is_consignment": True,
            "order_line": [(0, 0, {
                "product_id": self.product.id,
                "product_uom_qty": 5,
            })],
        })
        order.action_confirm()
        self.assertEqual(order.invoice_status, "no",
                         "a Pedido C must never look invoiceable")
        self.assertFalse(order._get_invoiceable_lines())
        with self.assertRaises(UserError):
            order._create_invoices()
