# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    """The stamp that makes a campaign measurable.

    Placement is a live calculation -- target of the running campaign against
    today's shelf -- and needs no trace. A SALE is not: it happens later, on
    another document, and no live calculation can attribute it back to the
    campaign that put the book on the shelf.

    So the campaigns that drove an operation are stamped on the orders it fires,
    at the moment it fires them. This costs nothing today. Without it, whatever
    goes out unstamped can never be attributed to anything, ever.
    """
    _inherit = 'sale.order'

    campaign_ids = fields.Many2many(
        'consignment.template', 'sale_order_campaign_rel', 'order_id', 'campaign_id',
        string='Campaigns', copy=False, readonly=True,
        help="The campaigns of the consignment operation that generated this "
             "order. On a replenishment (C) they are the reason it went out; on a "
             "sale (S) they were running on the shelf that sold.")


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        """The acerto's revenue sale never delivers from the warehouse.

        The physical baixa already happened off the customer's shelf -- the
        ACERTO picking the operation (CO) validated. Letting this sale confirm
        its own WH/OUT delivery would move the same books a second time and drag
        the acerto back into the warehouse, which is exactly what an acerto must
        not do: it only draws down the customer's shelf. The sale exists to
        invoice (invoice_policy 'order'), not to deliver.

        Only the acerto's *revenue* sale is held back (consignment_operation_id
        set, is_consignment False). The consignment Pedidos (C) still deliver
        normally -- they physically refill the shelf.
        """
        deliverable = self.filtered(
            lambda l: not (l.order_id.consignment_operation_id
                           and not l.order_id.is_consignment))
        return super(SaleOrderLine, deliverable)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty)
