# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    edlab_legacy_line_id = fields.Many2one(
        "edlab.contract.royalty.line",
        string="Legacy Accrual Of",
        index=True,
        ondelete="cascade",
        help="Set on the entries that accrue royalties from the legacy sales "
        "base (before Odoo), one per month of sales.",
    )
    edlab_legacy_period = fields.Char(
        string="Legacy Month", size=7, index=True,
        help="Month of the legacy sales this entry accrues, as YYYY-MM. With "
        "the royalty line, the key that makes the booking idempotent.")
    edlab_legacy_base = fields.Float(
        string="Legacy Base (nominal)", digits=(16, 2),
        help="Sum of the month's sales in the money of the time, before the "
        "price-index correction.")
    edlab_legacy_factor = fields.Float(
        string="Correction Factor", digits=(16, 6),
        help="Price-index factor applied to the nominal base (1 = none).")
