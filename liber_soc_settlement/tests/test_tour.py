# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestAcertoTour(HttpCase):
    """The acerto, on screen, to the end: a shelf with two titles goes in, and
    three correctly-typed documents come out.

    The tour types the decision (what sold, what comes back); this seeds the
    world around it and checks what the Run actually produced. The stat buttons
    the tour sees only prove a document was linked -- these assertions prove it
    is the RIGHT document, with the right title and quantity, and that the map
    the customer was settled against was pinned.
    """

    def _place_on_shelf(self, partner, product, qty):
        """Ship `qty` to the customer's shelf through the engine (a shipment
        released and validated), not by writing quants: the tour must settle
        against a shelf that got there the way a real one does."""
        shipment = self.env["consignment.move"].create({
            "partner_id": partner.id,
            "move_kind": "shipment",
            "line_ids": [(0, 0, {
                "product_id": product.id,
                "product_uom_qty": qty,
                "product_uom": product.uom_id.id,
            })],
        })
        shipment.action_confirm()
        shipment.action_release()
        shipment.picking_id.move_ids.picked = True
        shipment.picking_id.button_validate()

    def _book(self, name, warehouse_qty):
        product = self.env["product.product"].create({
            "name": name,
            "type": "consu",
            "is_storable": True,
            "list_price": 50.0,
        })
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1)
        # Stock the warehouse well above what the acerto sends back: the Run
        # must not stop on the overstock wizard (that guard is tested apart).
        self.env["stock.quant"].with_context(inventory_mode=True).create({
            "product_id": product.id,
            "location_id": warehouse.lot_stock_id.id,
            "inventory_quantity": warehouse_qty,
        }).action_apply_inventory()
        return product

    def test_soc_acerto_tour(self):
        partner = self.env["res.partner"].create({
            "name": "Livraria do Acerto", "is_company": True})
        agreement = self.env["consignment.agreement"].create({
            "partner_id": partner.id})
        agreement.action_activate()

        # The two fates of a consigned book, on the same shelf.
        sells = self._book("Livro que Vende", 40)
        stuck = self._book("Livro Parado", 20)
        self._place_on_shelf(partner, sells, 10)
        self._place_on_shelf(partner, stuck, 5)
        self.assertEqual(agreement.on_shelf_qty, 15,
                         "the seed must leave both titles on the shelf")

        self.start_tour("/odoo", "soc_acerto_tour", login="admin")

        settlement = self.env["consignment.settlement"].search(
            [("partner_id", "=", partner.id)], limit=1)
        self.assertTrue(settlement, "the tour must have created the operation")
        self.assertEqual(settlement.state, "confirmed")

        # Sold -> a real sale, of exactly what was reported, of the title that sold.
        sale = settlement.sale_order_id
        self.assertTrue(sale, "reporting 4 sold must create a sale order")
        self.assertEqual(sale.order_line.product_id, sells)
        self.assertEqual(sale.order_line.product_uom_qty, 4)
        # ...and the shelf baixa that goes with it (not a warehouse delivery).
        self.assertTrue(settlement.delivery_picking_id,
                        "the sale must draw the copies off the shelf")

        # Place -> a replenishment Pedido: a movement, never a sale.
        replenishment = settlement.replenishment_order_id
        self.assertTrue(replenishment, "the suggested Place must fire a Pedido")
        self.assertTrue(replenishment.is_consignment,
                        "the replenishment is a consignment Pedido (C), not a sale")
        self.assertEqual(replenishment.order_line.product_id, sells)
        self.assertEqual(replenishment.order_line.product_uom_qty, 4,
                         "the shelf keeps its size: resend what was sold")

        # Recalled -> a return movement, pure stock, of the title that did NOT sell.
        return_move = settlement.return_move_id
        self.assertTrue(return_move, "the recalled title must create a CR")
        self.assertEqual(return_move.move_kind, "return")
        self.assertEqual(return_move.line_ids.product_id, stuck)
        self.assertEqual(return_move.line_ids.product_uom_qty, 2)

        # The map was frozen on the Run: what the customer was settled against
        # must survive the shelf moving underneath it.
        frozen = {l.product_id: l.qty_on_shelf_frozen for l in settlement.line_ids}
        self.assertEqual(frozen[sells], 10)
        self.assertEqual(frozen[stuck], 5)
