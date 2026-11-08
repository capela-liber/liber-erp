# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    contract_license_product_id = fields.Many2one(
        related="company_id.contract_license_product_id", readonly=False)
    contract_license_account_id = fields.Many2one(
        related="company_id.contract_license_account_id", readonly=False)
    contract_license_journal_id = fields.Many2one(
        related="company_id.contract_license_journal_id", readonly=False)
