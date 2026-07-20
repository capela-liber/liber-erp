# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Per-company settings, surfaced in Settings > Copyright. They still live on
    # res.company (that is where a multi-company database has to keep them); this
    # is the place people actually look for them.
    contract_payment_product_id = fields.Many2one(
        related="company_id.contract_payment_product_id", readonly=False)
    contract_payment_account_id = fields.Many2one(
        related="company_id.contract_payment_account_id", readonly=False)
    contract_payment_journal_id = fields.Many2one(
        related="company_id.contract_payment_journal_id", readonly=False)
    contract_payment_days = fields.Integer(
        related="company_id.contract_payment_days", readonly=False)
