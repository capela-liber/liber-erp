# -*- coding: utf-8 -*-
"""Legacy accruals on the royalty line's analytic account.

One analytic entry per MONTH of legacy sales, not per row: the base has
half a million lines and an author's statement needs the month, not the
invoice. The entry is keyed by (royalty line, YYYY-MM) and refreshed on
every run, because the base is a dataset the department corrects and
re-imports -- unlike an invoice, which never changes once paid."""
import calendar
from datetime import date

from odoo import _, fields, models
from odoo.fields import Domain
from odoo.tools import float_compare


class EdlabContractRoyaltyLine(models.Model):
    _inherit = "edlab.contract.royalty.line"

    def _edlab_legacy_totals(self):
        """Monthly totals of this line's work in the legacy base, within the
        contract's legacy window. Empty when the contract does not opt in."""
        self.ensure_one()
        contract = self.contract_id
        if not (contract.legacy_enabled and self.product_id) \
                or contract.state == "cancelled":
            return []
        return self.env["edlab.legacy.sale"].sudo()._monthly_totals(
            self.product_id, contract.legacy_date_from, contract.legacy_date_to,
            company=contract.company_id)

    def _edlab_initial_cumulative_qty(self):
        """Legacy copies open the running total that selects the tier of
        the invoiced sales: an author whose book sold 3.000 copies before
        Odoo is not back at copy #1 on the first invoice here."""
        self.ensure_one()
        total = super()._edlab_initial_cumulative_qty()
        return total + sum(row["qty"] for row in self._edlab_legacy_totals())

    def _edlab_accrual_entry_domain(self):
        """Legacy entries are accruals too: the payment cutoff settles them
        and the author's statement lists them. Returned as a plain list,
        because the statement appends its date bounds to it."""
        self.ensure_one()
        return list(Domain.OR([
            super()._edlab_accrual_entry_domain(),
            [("account_id", "=", self.analytic_account_id.id),
             ("edlab_legacy_line_id", "!=", False)],
        ]))

    def _edlab_book_legacy(self):
        """Book (or refresh) the legacy accruals of these royalty lines.

        Returns ``(created, updated, removed)`` counts. Months that stop
        existing in the base (or fall out of the contract's window) lose
        their entry, so the account always mirrors the current base."""
        AnalyticLine = self.env["account.analytic.line"].sudo()
        created = updated = removed = 0
        for royalty in self:
            account = royalty.analytic_account_id
            contract = royalty.contract_id
            existing = {
                line.edlab_legacy_period: line
                for line in AnalyticLine.search(
                    [("edlab_legacy_line_id", "=", royalty.id)])}
            rows = royalty._edlab_legacy_totals() if account and royalty.tier_ids else []
            index = contract.legacy_index_id
            variations = index._variations() if index else None
            reference = contract._edlab_legacy_reference_date()
            cumulative = 0.0
            seen = set()
            for row in rows:
                month = row["month"]
                period = month.strftime("%Y-%m")
                seen.add(period)
                cumulative += row["qty"]
                # More returns than sales so far (a window opening on a
                # return) is a running total below zero: the first tier,
                # not the engine's "no tier matched -> last tier" fallback.
                percentage = royalty._royalty_percentage_for_qty(max(cumulative, 0.0))
                # On the cover price, special sales still pay on the net --
                # the invoices' rule; base_sales_price already applies it.
                base = row["base_sales_price"] if royalty.on_sales_price else row["base_net"]
                factor = index.factor(month, reference, variations) if index else 1.0
                amount = -(base * factor * percentage / 100.0)
                last_day = date(month.year, month.month,
                                calendar.monthrange(month.year, month.month)[1])
                name = _("Legacy sales %(month)s (%(pct).2f%%)",
                         month=month.strftime("%m/%Y"), pct=percentage)
                if index:
                    name += " x %.6f %s" % (factor, index.code)
                vals = {
                    "name": name,
                    "account_id": account.id,
                    "auto_account_id": account.id,
                    "date": last_day,
                    "amount": amount,
                    "unit_amount": row["qty"],
                    "partner_id": royalty.partner_id.id,
                    "product_id": royalty.product_id.product_variant_id.id,
                    "company_id": royalty.company_id.id,
                    "edlab_royalty_percentage": percentage,
                    "ref": _("Legacy"),
                    "edlab_legacy_line_id": royalty.id,
                    "edlab_legacy_period": period,
                    "edlab_legacy_base": base,
                    "edlab_legacy_factor": factor,
                }
                line = existing.get(period)
                if not line:
                    AnalyticLine.create(vals)
                    created += 1
                elif (float_compare(line.amount, amount, precision_digits=2)
                      or float_compare(line.unit_amount, row["qty"], precision_digits=2)
                      or line.date != last_day
                      or float_compare(line.edlab_royalty_percentage, percentage,
                                       precision_digits=2)):
                    line.write(vals)
                    updated += 1
            stale = AnalyticLine.concat(*[
                line for period, line in existing.items() if period not in seen])
            removed += len(stale)
            stale.unlink()
        return created, updated, removed

    def _edlab_unbook_legacy(self):
        lines = self.env["account.analytic.line"].sudo().search(
            [("edlab_legacy_line_id", "in", self.ids)])
        count = len(lines)
        lines.unlink()
        return count

    def _edlab_legacy_accrued(self):
        """Royalties accrued so far from the legacy base (positive)."""
        self.ensure_one()
        lines = self.env["account.analytic.line"].sudo().search(
            [("edlab_legacy_line_id", "=", self.id)])
        return -sum(lines.mapped("amount"))
