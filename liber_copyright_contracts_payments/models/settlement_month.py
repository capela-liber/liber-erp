# -*- coding: utf-8 -*-
import calendar
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class EdlabContractMonth(models.Model):
    """The twelve months, as records: the contract marks the ones that CLOSE
    a royalty period. Records (and not twelve booleans or a "3,9" string)
    because the question that matters is "which contracts close in
    October?" -- a search and a group-by, which only a relation answers."""
    _name = "edlab.contract.month"
    _description = "Month"
    _order = "number"

    name = fields.Char(required=True, translate=True)
    number = fields.Integer(required=True)

    _number_uniq = models.Constraint("unique(number)", "Each month exists once.")


class EdlabContract(models.Model):
    _inherit = "edlab.contract"

    settlement_month_ids = fields.Many2many(
        "edlab.contract.month",
        "edlab_contract_settlement_month_rel",
        "contract_id",
        "month_id",
        string="Closing Months",
        help="Months in which a royalty period of this contract CLOSES. "
        "June and December = semiannual; only December = annual.",
    )
    settlement_periodicity = fields.Selection(
        [
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("semiannual", "Semiannual"),
            ("annual", "Annual"),
            ("custom", "Custom"),
        ],
        string="Settlement Periodicity",
        compute="_compute_settlement_periodicity",
        store=True,
        help="Read from the closing months: evenly spaced months give a "
        "named periodicity; anything else is custom.",
    )
    next_closing_date = fields.Date(
        string="Next Closing",
        compute="_compute_next_closing_date",
        help="Last day of the next closing month (this month included).",
    )

    @api.depends("settlement_month_ids")
    def _compute_settlement_periodicity(self):
        named = {12: "monthly", 4: "quarterly", 2: "semiannual", 1: "annual"}
        for contract in self:
            months = sorted(contract.settlement_month_ids.mapped("number"))
            count = len(months)
            if not count:
                contract.settlement_periodicity = False
                continue
            step = 12 // count if 12 % count == 0 else 0
            gaps = [(months[(i + 1) % count] - months[i]) % 12 or 12 for i in range(count)]
            if count in named and all(g == step for g in gaps):
                contract.settlement_periodicity = named[count]
            else:
                contract.settlement_periodicity = "custom"

    @api.depends("settlement_month_ids")
    def _compute_next_closing_date(self):
        today = fields.Date.context_today(self)
        for contract in self:
            contract.next_closing_date = contract._edlab_next_closing(today)

    def _edlab_next_closing(self, today):
        self.ensure_one()
        numbers = set(self.settlement_month_ids.mapped("number"))
        if not numbers:
            return False
        first = date(today.year, today.month, 1)
        for ahead in range(12):
            month = first + relativedelta(months=ahead)
            if month.month in numbers:
                last = calendar.monthrange(month.year, month.month)[1]
                return date(month.year, month.month, last)
        return False
