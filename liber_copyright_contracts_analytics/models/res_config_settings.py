# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Per-company settings, surfaced in Settings > Copyright. The values still
    # live on res.company -- that is what makes them per-company -- and the
    # company selector at the top of Settings picks which one you are editing.
    contract_analytic_group_id = fields.Many2one(
        related="company_id.contract_analytic_group_id", readonly=False)
    contract_royalty_general_account_id = fields.Many2one(
        related="company_id.contract_royalty_general_account_id", readonly=False)
    contract_royalty_liability_account_id = fields.Many2one(
        related="company_id.contract_royalty_liability_account_id", readonly=False)
    contract_royalty_liability_months = fields.Integer(
        related="company_id.contract_royalty_liability_months", readonly=False)
    contract_special_sales_team_ids = fields.Many2many(
        related="company_id.contract_special_sales_team_ids", readonly=False)
    contract_special_min_discount = fields.Float(
        related="company_id.contract_special_min_discount", readonly=False)
