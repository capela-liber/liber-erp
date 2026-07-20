# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Per-company, surfaced in Settings > Copyright (see the analytics layer).
    contract_tax_partner_id = fields.Many2one(
        related="company_id.contract_tax_partner_id", readonly=False)
    contract_tax_account_id = fields.Many2one(
        related="company_id.contract_tax_account_id", readonly=False)
    contract_tax_journal_id = fields.Many2one(
        related="company_id.contract_tax_journal_id", readonly=False)
    contract_tax_due_day = fields.Integer(
        related="company_id.contract_tax_due_day", readonly=False)
