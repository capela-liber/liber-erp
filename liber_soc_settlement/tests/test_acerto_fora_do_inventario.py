# -*- coding: utf-8 -*-
"""The acerto baixa keeps its document and loses its card.

The commercial team opened the Inventory Overview and found an "Acerto de
Consignação" sitting next to Receipts and Delivery Orders, as if it were a
warehouse job waiting for somebody to confirm it. It never was: the transfer is
created AND validated inside the same Run click.

So the operation type is archived (decision of 13/08/2026, option A). What these
tests pin is that archiving buys the card and costs nothing else -- the shelf is
still debited, through a transfer that still has a name and a number.
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAcertoForaDoInventario(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': 'Livro do Acerto', 'type': 'consu', 'is_storable': True,
            'list_price': 50.0})

    def _agreement(self):
        partner = self.env['res.partner'].create({
            'name': 'Livraria sem Card', 'is_company': True})
        agreement = self.env['consignment.agreement'].create({
            'partner_id': partner.id, 'company_id': self.company.id,
            'date_start': fields.Date.today() - timedelta(days=1),
        })
        agreement.action_activate()
        return agreement

    def _place_on_shelf(self, partner, qty):
        """Ship to the shelf through the engine, not by writing quants: the
        acerto must settle against a shelf that got there the way a real one
        does."""
        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.product.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'inventory_quantity': qty + 10,
        }).action_apply_inventory()
        shipment = self.env['consignment.move'].create({
            'partner_id': partner.id,
            'move_kind': 'shipment',
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': qty,
                'product_uom': self.product.uom_id.id,
            })],
        })
        shipment.action_confirm()
        shipment.action_release()
        shipment.picking_id.move_ids.picked = True
        shipment.picking_id.button_validate()

    # ------------------------------------------------------------------

    def test_operation_type_is_born_off_the_overview(self):
        """The Inventory Overview lists the picking types a default search
        returns. Archived is exactly how a record stays out of one."""
        operation_type = self.company._get_consignment_settlement_operation_type()

        self.assertTrue(operation_type,
                        "the settlement still needs its own operation type")
        self.assertFalse(
            operation_type.active,
            "the acerto is not a warehouse job and must not draw a card")
        self.assertNotIn(
            operation_type, self.env['stock.picking.type'].search([]),
            "an active-tested search is what the Overview kanban runs")

    def test_the_type_is_created_once_and_reused(self):
        """Archiving must not make the getter think it is missing and mint a
        second one on every acerto."""
        first = self.company._get_consignment_settlement_operation_type()
        second = self.company._get_consignment_settlement_operation_type()

        self.assertEqual(first, second)

    def test_the_shelf_baixa_still_happens(self):
        """The whole point of option A: the card goes, the movement stays."""
        agreement = self._agreement()
        self._place_on_shelf(agreement.partner_id, 5)
        settlement = self.env['consignment.settlement'].create({
            'partner_id': agreement.partner_id.id,
            'company_id': self.company.id})
        settlement.action_populate_from_shelf()
        line = settlement.line_ids
        self.assertEqual(line.qty_on_shelf, 5, "the map must see the shelf")
        line.qty_reported = 2

        settlement.action_run()

        picking = settlement.delivery_picking_id
        self.assertTrue(picking, "the sale must draw the copies off the shelf")
        self.assertEqual(picking.state, 'done',
                         "the Run validates it -- nobody confirms it by hand")
        self.assertFalse(picking.picking_type_id.active,
                         "and it does so on the archived type")
        self.assertTrue(picking.name.startswith('ACERTO/'),
                        "the baixa keeps its own numbering, not WH/OUT")
        on_shelf = sum(self.env['stock.quant'].search([
            ('location_id', '=', settlement.location_id.id),
            ('product_id', '=', self.product.id)]).mapped('quantity'))
        self.assertEqual(on_shelf, 3,
                         "what the customer sold must leave the shelf")

    def test_the_acerto_sale_still_does_not_deliver(self):
        """The other half of the rule: no WH/OUT behind the S.

        Since 19.0.2.9.0 the baixa's moves carry sale_line_id (so the sale
        can invoice what left the shelf), which makes the ACERTO/ picking
        show up as the S's transfer -- truthfully. What must NEVER show up
        is a warehouse delivery."""
        agreement = self._agreement()
        self._place_on_shelf(agreement.partner_id, 4)
        settlement = self.env['consignment.settlement'].create({
            'partner_id': agreement.partner_id.id,
            'company_id': self.company.id})
        settlement.action_populate_from_shelf()
        settlement.line_ids.qty_reported = 1

        settlement.action_run()

        self.assertEqual(
            settlement.sale_order_id.picking_ids,
            settlement.delivery_picking_id,
            "the S's only transfer is the shelf baixa; the acerto sale "
            "invoices, it does not deliver from the warehouse")
