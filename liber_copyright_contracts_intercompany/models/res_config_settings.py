# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Per-company, surfaced in Settings > Copyright (see the analytics layer).
    contract_interco_source_company_ids = fields.Many2many(
        related="company_id.contract_interco_source_company_ids",
        readonly=False)
    contract_interco_product_id = fields.Many2one(
        related="company_id.contract_interco_product_id", readonly=False)
    # The domains declared on res.company cannot be reused as-is: their
    # "('company_id', '=', id)" refers to the COMPANY's id, which here is the
    # settings record's. Restated against company_id, they are what stops a
    # bank journal or a cash account from being picked -- a wrong journal type
    # makes Odoo refuse the document outright.
    contract_interco_journal_id = fields.Many2one(
        related="company_id.contract_interco_journal_id", readonly=False,
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]")
    contract_interco_income_account_id = fields.Many2one(
        related="company_id.contract_interco_income_account_id", readonly=False,
        domain="[('account_type', 'in', ('income', 'income_other')),"
               " ('company_ids', 'in', company_id)]")
    contract_interco_markup = fields.Float(
        related="company_id.contract_interco_markup", readonly=False)
    contract_interco_purchase_journal_id = fields.Many2one(
        related="company_id.contract_interco_purchase_journal_id",
        readonly=False,
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]")
    contract_interco_expense_account_id = fields.Many2one(
        related="company_id.contract_interco_expense_account_id",
        readonly=False,
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost',"
               " 'expense_depreciation')), ('company_ids', 'in', company_id)]")
