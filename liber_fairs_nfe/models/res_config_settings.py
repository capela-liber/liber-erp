# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fair_shipment_fiscal_position_id = fields.Many2one(
        related='company_id.fair_shipment_fiscal_position_id', readonly=False)
    fair_return_fiscal_position_id = fields.Many2one(
        related='company_id.fair_return_fiscal_position_id', readonly=False)
