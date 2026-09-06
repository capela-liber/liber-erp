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
        # A busca fica com os direitos de quem chamou: ler stock.location é de
        # todo empregado, e passar sudo aqui atravessaria a regra de empresa.
        root = self.search([
            ('is_consignment_root', '=', True),
            ('company_id', '=', company.id),
        ], limit=1)
        if not root:
            # sudo DELIBERADO: criar stock.location é direito de
            # Inventário/Administrador, e quem fecha um contrato de
            # consignação é do Comercial. A raiz CO não é uma gaveta que
            # alguém abriu no Inventário -- é infraestrutura deste módulo,
            # nascida como consequência do contrato, com nome e forma fixos
            # aqui. Sem isto a ativação morre em Access Error na tela, que foi
            # o que aconteceu com a gerente comercial em 26/08/2026.
            root = self.sudo().create({
                'name': 'CO',
                'usage': 'view',
                'location_id': False,
                'company_id': company.id,
                'is_consignment_root': True,
            })
            return root.sudo(False)
        if root.location_id:
            root.sudo().location_id = False
            # ``warehouse_id`` is stored and depends on the parent chain, but Odoo
            # does not cascade its recompute to the shelves below; left stale, they
            # would keep claiming to belong to the warehouse they just left.
            self.search([('id', 'child_of', root.id)]).sudo()._compute_warehouse_id()
        return root
