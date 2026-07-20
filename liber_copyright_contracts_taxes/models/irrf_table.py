# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.tools import float_round


class EdlabIrrfTable(models.Model):
    _name = "edlab.irrf.table"
    _description = "IRRF Progressive Table"
    _order = "date_from desc"

    name = fields.Char(required=True)
    date_from = fields.Date(
        string="Valid From",
        required=True,
        help="The table applies to bills dated on or after this date "
        "(until a more recent table starts).",
    )
    simplified_discount = fields.Float(
        string="Simplified Discount",
        digits=(16, 2),
        help="Fixed amount subtracted from the monthly income to obtain the "
        "tax base (accountant's method - no dependent deduction).",
    )
    no_withholding_limit = fields.Float(
        string="No Withholding Up To",
        digits=(16, 2),
        help="Monthly income up to this amount is NOT withheld at all "
        "(hard cutoff, computed before anything else).",
    )
    reducer_a = fields.Float(
        string="Reducer Constant (A)",
        digits=(16, 6),
        help="Reducer formula: A - B x income (Lei 15.270/2025).",
    )
    reducer_b = fields.Float(
        string="Reducer Factor (B)",
        digits=(16, 6),
        help="Reducer formula: A - B x income (Lei 15.270/2025).",
    )
    reducer_cap_limit = fields.Float(
        string="Reducer Up To",
        digits=(16, 2),
        help="The reducer applies to incomes up to this amount; above it the "
        "table value is final.",
    )
    bracket_ids = fields.One2many(
        "edlab.irrf.bracket",
        "table_id",
        string="Brackets",
        copy=True,
    )

    @api.model
    def _table_for_date(self, date=None):
        """Table in force at `date`: the most recent one started by then."""
        date = date or fields.Date.context_today(self)
        table = self.search([("date_from", "<=", date)], limit=1)
        return table or self.search([], order="date_from asc", limit=1)

    def _tax_for_income(self, income):
        """IRRF for a monthly income, per the accountant's method:
        cutoff, simplified discount, progressive table, then the reducer."""
        self.ensure_one()
        if income <= self.no_withholding_limit:
            return 0.0
        base = income - self.simplified_discount
        tax = 0.0
        for bracket in self.bracket_ids.sorted(
            key=lambda b: b.amount_to or float("inf")
        ):
            if not bracket.amount_to or base <= bracket.amount_to:
                tax = base * bracket.rate / 100.0 - bracket.deductible
                break
        if income <= self.reducer_cap_limit:
            reducer = max(self.reducer_a - self.reducer_b * income, 0.0)
            tax -= reducer
        return max(float_round(tax, precision_digits=2), 0.0)

    @api.model
    def _irrf_for_partner(self, partner, income, date=None):
        """IRRF withheld from `income` paid to `partner`, honouring the
        beneficiary's mode: progressive table (default), manual percentage
        (the legacy fixed field) or exempt."""
        mode = partner.edlab_irrf_mode or "table"
        if mode == "none" or income <= 0:
            return 0.0
        if mode == "manual":
            pct = partner.edlab_irrf_percentage or 0.0
            return max(float_round(income * pct / 100.0, precision_digits=2), 0.0)
        table = self._table_for_date(date)
        if not table:
            return 0.0
        return table._tax_for_income(income)


class EdlabIrrfBracket(models.Model):
    _name = "edlab.irrf.bracket"
    _description = "IRRF Table Bracket"
    _order = "amount_to"

    table_id = fields.Many2one(
        "edlab.irrf.table",
        required=True,
        ondelete="cascade",
        index=True,
    )
    amount_to = fields.Float(
        string="Base Up To",
        digits=(16, 2),
        help="Upper bound of the tax base for this bracket. 0 = no limit "
        "(top bracket).",
    )
    rate = fields.Float(string="Rate (%)", digits=(5, 2))
    deductible = fields.Float(
        string="Deductible",
        digits=(16, 2),
        help="Fixed amount subtracted after applying the rate "
        "(parcela a deduzir).",
    )
