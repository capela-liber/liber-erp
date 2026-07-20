# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    consignment_stock_account_id = fields.Many2one(
        'account.account', string='Consignment Stock Account',
        domain="[('account_type', '=', 'asset_current')]",
        help="Asset account that holds the value of goods currently consigned at "
             "customers (e.g. 115000). Consignment shelves re-qualify their value "
             "into this account instead of the warehouse Inventory account.")

    # --- Consignment fiscal parametrization -------------------------------
    # One fiscal position per operation (the same inside/outside the state);
    # only the CFOP splits internal (5xxx) vs interstate (6xxx). Accounts flow
    # through the fiscal position mapping, so no loose account fields are needed.
    consignment_shipment_fiscal_position_id = fields.Many2one(
        'account.fiscal.position', string='Shipment — Fiscal Position',
        help="Fiscal position for the consignment shipment (Pedido C).")
    consignment_shipment_cfop_in_id = fields.Many2one(
        'nfe.cfop', string='Shipment — CFOP (domestic)', domain=[('code', '=like', '5%')])
    consignment_shipment_cfop_out_id = fields.Many2one(
        'nfe.cfop', string='Shipment — CFOP (interstate)', domain=[('code', '=like', '6%')])

    consignment_sale_fiscal_position_id = fields.Many2one(
        'account.fiscal.position', string='Settlement (Sale) — Fiscal Position',
        help="Fiscal position for the sale generated at settlement (Acerto S).")
    consignment_sale_cfop_in_id = fields.Many2one(
        'nfe.cfop', string='Settlement — CFOP (domestic)', domain=[('code', '=like', '5%')])
    consignment_sale_cfop_out_id = fields.Many2one(
        'nfe.cfop', string='Settlement — CFOP (interstate)', domain=[('code', '=like', '6%')])

    consignment_return_fiscal_position_id = fields.Many2one(
        'account.fiscal.position', string='Return — Fiscal Position',
        help="Fiscal position for the consignment return.")
    consignment_return_cfop_in_id = fields.Many2one(
        'nfe.cfop', string='Return — CFOP (domestic)', domain=[('code', '=like', '5%')])
    consignment_return_cfop_out_id = fields.Many2one(
        'nfe.cfop', string='Return — CFOP (interstate)', domain=[('code', '=like', '6%')])

    def action_wire_consignment_shelves(self):
        """Set valuation_account_id = consignment_stock_account_id on every
        existing consignment shelf of the company (backfill)."""
        Location = self.env['stock.location']
        for company in self:
            account = company.consignment_stock_account_id
            if not account:
                continue
            shelves = Location.search([
                ('is_consignment_shelf', '=', True),
                ('company_id', '=', company.id),
            ])
            shelves.write({'valuation_account_id': account.id})
        return True
