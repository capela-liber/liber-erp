# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Freight choice captured at quote time; the purchase payload reads these.
    # Proper snake_case names -- the O15 'shippment_supplier' typo family is
    # not migrated.
    metabrasil_carrier_name = fields.Char(
        string='PoD Carrier', copy=False, readonly=True)
    metabrasil_carrier_vat = fields.Char(
        string='PoD Carrier CNPJ', copy=False, readonly=True)
    metabrasil_carrier_code = fields.Integer(
        string='PoD Carrier Code', copy=False, readonly=True)
    metabrasil_service_code = fields.Integer(
        string='PoD Service Code', copy=False, readonly=True)
    metabrasil_delivery_days = fields.Integer(
        string='PoD Delivery Days', copy=False, readonly=True)
    metabrasil_freight_cost = fields.Float(
        string='PoD Freight Cost', copy=False, readonly=True,
        help="Raw freight quoted by Metabrasil, before the carrier margin.")
    metabrasil_total_weight = fields.Float(
        string='PoD Weight (kg)', copy=False, readonly=True)
    metabrasil_total_volumes = fields.Integer(
        string='PoD Volumes', copy=False, readonly=True)
    is_metabrasil = fields.Boolean(
        string='Has Print Products', compute='_compute_is_metabrasil',
        help="A line's product is supplied by the Metabrasil printer. Drives "
             "the print-order smart button and the Dropship ribbon.")

    @api.depends('order_line.product_id', 'company_id.metabrasil_enabled',
                 'company_id.metabrasil_partner_id')
    def _compute_is_metabrasil(self):
        for so in self:
            printer = so.company_id.metabrasil_partner_id
            so.is_metabrasil = bool(
                so.company_id.metabrasil_enabled and printer
                and any(printer in line.product_id.seller_ids.partner_id
                        for line in so.order_line if line.product_id))

    metabrasil_delivery_kind = fields.Selection(
        [('warehouse', 'PoD'), ('customer', 'Dropship')],
        string='Print Delivery Kind', compute='_compute_metabrasil_delivery_kind',
        help="Whether this sale prints straight to the customer (dropship) or "
             "to our depot. Read from the dropship route on the line's product "
             "-- the same route that actually spawns the print order -- so the "
             "ribbon tells the truth without anyone having to declare it.")

    @api.depends('is_metabrasil', 'order_line.product_id')
    def _compute_metabrasil_delivery_kind(self):
        dropship = self.env.ref('stock_dropshipping.route_drop_shipping',
                                raise_if_not_found=False)
        for so in self:
            if not so.is_metabrasil:
                so.metabrasil_delivery_kind = False
            elif dropship and any(dropship in line.product_id.route_ids
                                  for line in so.order_line if line.product_id):
                so.metabrasil_delivery_kind = 'customer'
            else:
                so.metabrasil_delivery_kind = 'warehouse'

    # ------------------------------------------------------------------
    # The print orders this sale spawned
    # ------------------------------------------------------------------
    # sale_purchase already ships a generic 'Purchase' smart button, but it
    # counts every purchase the sale generated and hides behind the purchase
    # group. The print run is the thing the commercial team follows, so it
    # gets its own button: only Metabrasil orders, and the print status
    # travels with it.
    metabrasil_purchase_order_ids = fields.Many2many(
        'purchase.order', string='Print Orders',
        compute='_compute_metabrasil_purchase_orders')
    metabrasil_purchase_order_count = fields.Integer(
        string='Print Order Count', compute='_compute_metabrasil_purchase_orders')

    @api.depends('order_line.purchase_line_ids.order_id',
                 'company_id.metabrasil_partner_id')
    def _compute_metabrasil_purchase_orders(self):
        for so in self:
            printer = so.company_id.metabrasil_partner_id
            orders = so.order_line.purchase_line_ids.order_id.filtered(
                lambda po: printer and po.partner_id == printer)
            so.metabrasil_purchase_order_ids = orders
            so.metabrasil_purchase_order_count = len(orders)

    def action_view_metabrasil_purchase_orders(self):
        self.ensure_one()
        orders = self.metabrasil_purchase_order_ids
        action = {'type': 'ir.actions.act_window',
                  'res_model': 'purchase.order'}
        if len(orders) == 1:
            action.update(view_mode='form', res_id=orders.id)
        else:
            action.update(
                name=self.env._("Print orders for %s", self.name),
                view_mode='list,form',
                domain=[('id', 'in', orders.ids)])
        return action

    # ------------------------------------------------------------------
    # Dropship with nobody to buy from: the silent one
    # ------------------------------------------------------------------
    # A title on the dropship route plans no delivery out of our stock --
    # the goods are supposed to leave the vendor's dock. Give it no vendor
    # and confirmation produces nothing at all: no purchase order, no
    # picking, not even a stock move. The customer is invoiced and the books
    # never exist. Odoo does say so, in a chatter line nobody reads, after
    # the fact. So: named on the quotation while it is still a quotation,
    # and refused at confirmation.
    metabrasil_dropship_warning = fields.Char(
        compute='_compute_metabrasil_dropship_warning')

    def _metabrasil_dropship_gap_lines(self):
        """Lines that would confirm into nothing at all."""
        self.ensure_one()
        dropship = self.env.ref('stock_dropshipping.route_drop_shipping',
                                raise_if_not_found=False)
        if not dropship:
            return self.env['sale.order.line']
        date = self.date_order.date() if self.date_order else None
        gaps = self.env['sale.order.line']
        for line in self.order_line:
            product = line.product_id
            if line.display_type or not product or product.type == 'service':
                continue
            # The route can arrive by three doors, and any of them is enough:
            # set on the line, on the product, or inherited from its category.
            routes = (line.route_ids | product.route_ids
                      | product.route_from_categ_ids)
            if dropship not in routes:
                continue
            # quantity=None skips the min_qty tiers on purpose: the question
            # is "is there anybody to buy from", not "does the price ladder
            # reach this print run" -- which is a different complaint, and
            # Odoo's own.
            if not product._select_seller(quantity=None, date=date):
                gaps |= line
        return gaps

    @api.depends('order_line.product_id', 'order_line.route_ids',
                 'order_line.product_id.route_ids',
                 'order_line.product_id.seller_ids')
    def _compute_metabrasil_dropship_warning(self):
        for so in self:
            gaps = so._metabrasil_dropship_gap_lines()
            so.metabrasil_dropship_warning = gaps and self.env._(
                "Dropship with no vendor: %s. Confirming would buy nothing "
                "and ship nothing. Give these products a vendor, or take "
                "them off the dropship route.",
                ", ".join(gaps.product_id.mapped('display_name'))) or False

    def _action_confirm(self):
        for order in self:
            gaps = order._metabrasil_dropship_gap_lines()
            if gaps:
                # Raising rolls the confirmation back, so the order stays a
                # quotation instead of becoming a sale that ships nothing.
                raise UserError(self.env._(
                    "%(order)s was not confirmed: these products are on the "
                    "dropship route but have no vendor, so nothing would be "
                    "bought and nothing would ship.\n\n%(products)s\n\n"
                    "Give them a vendor, or take them off the dropship "
                    "route.",
                    order=order.name,
                    products="\n".join(
                        "- %s" % name
                        for name in gaps.product_id.mapped('display_name'))))
        return super()._action_confirm()

    def _metabrasil_quote_items(self):
        """listaItems for /fretes and the order POST: storable lines only
        (freight and other services never ship in a box)."""
        self.ensure_one()
        return [{
            'preco': float(line.price_unit),
            'quantidade': float(line.product_uom_qty),
            'referenciaISBN': str(line.product_id.barcode
                                  or line.product_id.default_code or ''),
        } for line in self.order_line
            if line.product_id.type != 'service' and not line.display_type]

    @api.onchange('carrier_id')
    def _onchange_carrier_metabrasil(self):
        # Selecting a non-Metabrasil carrier invalidates a Metabrasil quote.
        for order in self:
            if order.carrier_id and order.carrier_id.delivery_type != 'metabrasil':
                order.metabrasil_carrier_name = False
                order.metabrasil_carrier_vat = False
                order.metabrasil_carrier_code = 0
                order.metabrasil_service_code = 0
