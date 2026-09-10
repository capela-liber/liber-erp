# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    # Related/stored (not a plain copy of company_id): it backfills existing
    # accruals on install and can never diverge from the sale it came from.
    # Only accruals carry it -- advance/cutoff/payment entries have no source
    # move line, so they stay empty and out of the intercompany charge.
    edlab_source_company_id = fields.Many2one(
        "res.company",
        string="Source Company",
        related="edlab_source_move_line_id.company_id",
        store=True,
        index=True,
        help="Company that made the sale this royalty accrued from. Sales of "
        "a company other than the contract's are charged back to it through "
        "the intercompany royalty invoice.",
    )
    edlab_interco_move_line_id = fields.Many2one(
        "account.move.line",
        string="Intercompany Charge Line",
        index=True,
        ondelete="set null",
        copy=False,
        help="Line of the intercompany royalty invoice charging this accrual "
        "to the selling company. Empty = not charged yet; pointing to a draft "
        "invoice = still accumulating; pointing to a posted invoice = frozen.",
    )
