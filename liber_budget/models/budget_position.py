# -*- coding: utf-8 -*-
from odoo import api, fields, models


class BudgetPosition(models.Model):
    """Budgetary position: a named set of general ledger accounts (like the
    pre-17 'account.budget.post'). A budget line pointing to a position reads
    its actuals straight from account.move.line -> works retroactively, no
    analytic tagging needed."""
    _name = 'budget.position'
    _description = "Budgetary Position"
    _order = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company)
    account_ids = fields.Many2many(
        'account.account', string="Accounts",
        help="General ledger accounts whose journal items feed this position.")
    account_count = fields.Integer(compute='_compute_account_count')

    @api.depends('account_ids')
    def _compute_account_count(self):
        for position in self:
            position.account_count = len(position.account_ids)
