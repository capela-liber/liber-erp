# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    consignment_adjustment_account_id = fields.Many2one(
        related='company_id.consignment_adjustment_account_id', readonly=False,
        string='Consignment Adjustment Account',
        help="P&L account that receives the value difference when an audit "
             "adjustment corrects the shelf (shrinkage or found stock).")
    consignment_adjustment_location_id = fields.Many2one(
        related='company_id.consignment_adjustment_location_id', readonly=False,
        string='Consignment Adjustment Location')
