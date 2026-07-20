# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    is_consignment_root = fields.Boolean(
        string='Consignment Root',
        help="Parent (view) location grouping all consignment customer shelves of the company.")
    is_consignment_shelf = fields.Boolean(
        string='Consignment Shelf',
        help="Internal location holding our stock physically placed at a customer.")
    consignment_partner_id = fields.Many2one(
        'res.partner', string='Consignee',
        help="Customer whose shelf this location represents.")

    @api.model
    def _soc_consignment_root(self, company):
        """The CO root: a top-level view location, deliberately OUTSIDE the warehouse.

        The goods on a consignment shelf are still ours (they stay in internal
        locations, so they keep their value on our books), but they are not in
        our hands: they sit at the bookshop. Odoo's On Hand / Forecasted count
        everything under the warehouse's view location, so a shelf hanging under
        WH would silently inflate On Hand with stock we cannot sell or ship.
        Keeping the root outside the warehouse tree is what excludes it -- no
        override of the core quantity computation is needed, and a shipment to a
        shelf reads as leaving the warehouse, which is exactly what it is.
        """
        root = self.search([
            ('is_consignment_root', '=', True),
            ('company_id', '=', company.id),
        ], limit=1)
        if not root:
            return self.create({
                'name': 'CO',
                'usage': 'view',
                'location_id': False,
                'company_id': company.id,
                'is_consignment_root': True,
            })
        if root.location_id:
            root.location_id = False
            # ``warehouse_id`` is stored and depends on the parent chain, but Odoo
            # does not cascade its recompute to the shelves below; left stale, they
            # would keep claiming to belong to the warehouse they just left.
            self.search([('id', 'child_of', root.id)])._compute_warehouse_id()
        return root
