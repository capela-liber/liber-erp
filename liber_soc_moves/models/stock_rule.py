# -*- coding: utf-8 -*-
from odoo import models


class StockRule(models.Model):
    """Route Pedido C deliveries onto the consignment operation type.

    The sale-stock rule chain stamps the warehouse's generic out type
    (WH/OUT, "Pedidos de entrega") on every delivery it spawns. For a
    consignment order that is wrong twice: the picking looks like a sale
    delivery to the warehouse crew, and its number says nothing about
    consignment. He caught it on C00003's WH/OUT/00006.

    Only the OUTGOING step is swapped: in a multi-step warehouse the pick/pack
    legs stay on their own types.
    """
    _inherit = 'stock.rule'

    def _get_stock_move_values(self, product_id, product_qty, product_uom,
                               location_dest_id, name, origin, company_id,
                               values):
        vals = super()._get_stock_move_values(
            product_id, product_qty, product_uom, location_dest_id, name,
            origin, company_id, values)
        # v19: the sale reaches the rule as values['sale_line_id'] (the
        # procurement group has no sale_id here).
        line_id = values.get('sale_line_id')
        sale = (self.env['sale.order.line'].browse(line_id).order_id
                if line_id else False)
        if sale and sale.is_consignment and vals.get('picking_type_id'):
            ptype = self.env['stock.picking.type'].browse(
                vals['picking_type_id'])
            if ptype.code == 'outgoing':
                delivery_type = \
                    company_id._get_consignment_delivery_operation_type()
                if delivery_type:
                    vals['picking_type_id'] = delivery_type.id
        return vals
