# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    edlab_royalty_percentage = fields.Float(
        string="Royalty %",
        digits=(5, 2),
        help="Royalty percentage applied, taken from the tier of the cumulative "
        "quantity of the work sold up to this invoice.",
    )
    edlab_source_move_line_id = fields.Many2one(
        "account.move.line",
        string="Source Invoice Line",
        index=True,
        ondelete="cascade",
        help="Invoice line this royalty analytic line was generated from. "
        "Used to avoid booking the same royalty twice.",
    )
    edlab_payment_cutoff_line_id = fields.Many2one(
        "edlab.contract.royalty.line",
        string="Payment Cutoff Of",
        index=True,
        ondelete="cascade",
        help="Set on the compensating entry that settles the royalty debt "
        "accrued up to the beneficiary's last payment date. Stands in for the "
        "bill that will settle it once the payment module exists.",
    )
    edlab_advance_line_id = fields.Many2one(
        "edlab.contract.royalty.line",
        string="Recoupable Advance Of",
        index=True,
        ondelete="cascade",
        help="Set on the opening entry that books this royalty line's "
        "recoupable advance (already paid to the beneficiary) as a positive "
        "amount, recouped as royalties accrue.",
    )

    # The native Financial Account mirrors the source journal item (move_line_id).
    # Royalty analytic lines have no journal item, so for them fall back to the
    # account configured in the company's copyright settings; every other line
    # keeps the standard behaviour (mirror the journal item, else empty).
    general_account_id = fields.Many2one(
        related=False,
        compute="_compute_general_account_id",
        store=True,
        readonly=True,
    )

    edlab_amount_charged = fields.Monetary(
        string="Royalty Charged",
        compute="_compute_edlab_split_amounts",
        store=True,
        currency_field="currency_id",
        help="Negative side of the amount: royalty accrued/owed.",
    )
    edlab_amount_paid = fields.Monetary(
        string="Royalty Paid",
        compute="_compute_edlab_split_amounts",
        store=True,
        currency_field="currency_id",
        help="Positive side of the amount: payments/settlements.",
    )

    @api.depends("amount")
    def _compute_edlab_split_amounts(self):
        for line in self:
            line.edlab_amount_charged = line.amount if line.amount < 0 else 0.0
            line.edlab_amount_paid = line.amount if line.amount > 0 else 0.0

    @api.depends(
        "move_line_id.account_id",
        "edlab_source_move_line_id",
        "edlab_payment_cutoff_line_id",
        "date",
        "company_id.contract_royalty_general_account_id",
        "company_id.contract_royalty_liability_account_id",
        "company_id.contract_royalty_liability_months",
    )
    def _compute_general_account_id(self):
        today = fields.Date.today()
        for line in self:
            if line.move_line_id.account_id:
                line.general_account_id = line.move_line_id.account_id
            elif line.edlab_source_move_line_id or line.edlab_payment_cutoff_line_id:
                line.general_account_id = line._royalty_financial_account(today)
            else:
                line.general_account_id = False

    def _royalty_financial_account(self, today=None):
        """Expense account normally; the liability account once the royalty is
        overdue by more than the company's configured number of months."""
        self.ensure_one()
        today = today or fields.Date.today()
        company = self.company_id
        expense = company.contract_royalty_general_account_id
        liability = company.contract_royalty_liability_account_id
        months_limit = company.contract_royalty_liability_months
        if liability and months_limit and self.date:
            delta = relativedelta(today, self.date)
            months_overdue = delta.years * 12 + delta.months
            if months_overdue > months_limit:
                return liability
        return expense

    @api.model
    def _cron_reclassify_royalty_accounts(self):
        """Daily: move royalty lines that crossed the liability threshold from
        the expense account to the liability account (and vice-versa)."""
        lines = self.search(
            [
                "|",
                ("edlab_source_move_line_id", "!=", False),
                ("edlab_payment_cutoff_line_id", "!=", False),
            ]
        )
        lines._compute_general_account_id()
        # v19: recordset.flush() is gone; flush_recordset() is its replacement.
        lines.flush_recordset(["general_account_id"])
