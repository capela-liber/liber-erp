# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    # The consignment *stock* account (115000) lives in soc_fiscal_br
    # (consignment_stock_account_id). Here we add the *adjustment* account: the
    # P&L side that absorbs the value difference when an audit corrects the map.
    consignment_adjustment_account_id = fields.Many2one(
        'account.account', string='Consignment Adjustment Account',
        domain="[('deprecated', '=', False)]",
        help="P&L account that receives the value difference when an audit "
             "adjustment corrects the shelf: shrinkage (debit) or found stock "
             "(credit), balanced against the Consignment Stock Account.")
    consignment_adjustment_location_id = fields.Many2one(
        'stock.location', string='Consignment Adjustment Location', copy=False,
        help="Inventory-type location the audit adjustments move stock to/from "
             "so the quantity correction is recorded in the stock history. "
             "Created automatically on first use. The value posting is a "
             "separate journal entry, so this location needs no valuation "
             "account.")

    def _get_consignment_adjustment_location(self):
        """Return (creating if needed) the inventory-usage location used to
        record the *quantity* side of audit adjustments.

        The shelf is a non-valued location (soc_fiscal_br) and this location is
        of ``inventory`` usage, so the stock move between them carries no
        automatic valuation -- the value is posted explicitly instead. That is
        deliberate: it keeps the accounting deterministic regardless of the
        product's valuation method.
        """
        self.ensure_one()
        location = self.consignment_adjustment_location_id
        if not location:
            location = self.env['stock.location'].sudo().create({
                'name': _('Consignment Adjustment'),
                'usage': 'inventory',
                'company_id': self.id,
            })
            self.consignment_adjustment_location_id = location.id
        return location

    def _get_consignment_adjustment_journal(self):
        self.ensure_one()
        journal = self.account_stock_journal_id or self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.id)], limit=1)
        if not journal:
            raise UserError(_(
                "No stock or general journal configured for company %s.")
                % self.display_name)
        return journal
