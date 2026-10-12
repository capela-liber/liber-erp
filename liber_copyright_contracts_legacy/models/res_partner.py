# -*- coding: utf-8 -*-
"""The author's statement gains a yearly view of the price-index correction.

The legacy entries are already in the statement total (they are accruals,
see royalty_line.py); what the author could not see was HOW MUCH of that
total is correction. This adds, per work and year, the copies, the nominal
base of the time, the corrected base, the effective factor between the two
and the royalty, so the author can read "2005: R$ 2.400 of sales became
R$ 8.600 of today's money, and 7% of that is what I am owed"."""
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _edlab_royalty_statement(self, date_to=None):
        res = super()._edlab_royalty_statement(date_to=date_to)
        res["legacy_years"] = self._edlab_legacy_year_rows(res.get("date_to"))
        currency = res["currency"]
        res["legacy_years_total"] = {
            "qty": sum(r["qty"] for r in res["legacy_years"]),
            "nominal": currency.round(sum(r["nominal"] for r in res["legacy_years"])),
            "corrected": currency.round(sum(r["corrected"] for r in res["legacy_years"])),
            "amount": currency.round(sum(r["amount"] for r in res["legacy_years"])),
        }
        return res

    def _edlab_legacy_year_rows(self, date_to=None):
        """One row per (work, contract, year) of legacy accruals still open
        at ``date_to`` -- the same window the statement itself covers (after
        the last payment, up to the period end)."""
        self.ensure_one()
        AnalyticLine = self.env["account.analytic.line"].sudo()
        currency = self.env.company.currency_id
        date_to = date_to or fields.Date.context_today(self)
        rows = []
        for line in self.edlab_royalty_line_ids.sorted(
            key=lambda l: (l.contract_id.name or "", l.product_id.display_name or "")
        ):
            if not line.analytic_account_id:
                continue
            domain = [("edlab_legacy_line_id", "=", line.id), ("date", "<=", date_to)]
            if line.last_payment_date:
                domain.append(("date", ">", line.last_payment_date))
            entries = AnalyticLine.search(domain, order="date")
            if not entries:
                continue
            contract = line.contract_id
            index = contract.legacy_index_id
            if index:
                reference = contract._edlab_legacy_reference_date()
                index_label = "%s %s" % (index.code, reference.strftime("%m/%Y"))
            else:
                index_label = "\N{EM DASH}"
            by_year = {}
            for entry in entries:
                year = entry.date.year
                bucket = by_year.setdefault(year, {
                    "qty": 0.0, "nominal": 0.0, "corrected": 0.0,
                    "amount": 0.0, "percentages": set()})
                bucket["qty"] += entry.unit_amount
                bucket["nominal"] += entry.edlab_legacy_base
                if entry.edlab_royalty_percentage:
                    bucket["corrected"] += (
                        -entry.amount * 100.0 / entry.edlab_royalty_percentage)
                    bucket["percentages"].add(entry.edlab_royalty_percentage)
                bucket["amount"] += -entry.amount
            for year in sorted(by_year):
                b = by_year[year]
                factor = (b["corrected"] / b["nominal"]) if b["nominal"] else 0.0
                pcts = sorted(b["percentages"])
                if len(pcts) == 1:
                    pct_label = ("%.2f" % pcts[0]).replace(".", ",") + "%"
                elif pcts:
                    pct_label = "%s a %s" % (
                        ("%.2f" % pcts[0]).replace(".", ","),
                        ("%.2f" % pcts[-1]).replace(".", ",") + "%")
                else:
                    pct_label = "\N{EM DASH}"
                qty = b["qty"]
                rows.append({
                    "line": line,
                    "work": line.product_id.display_name,
                    "contract": contract.name,
                    "year": year,
                    "index_label": index_label,
                    "qty": int(qty) if qty == int(qty) else qty,
                    "nominal": currency.round(b["nominal"]),
                    "factor": factor,
                    "factor_label": ("%.4f" % factor).replace(".", ",") if factor else "\N{EM DASH}",
                    "corrected": currency.round(b["corrected"]),
                    "percentage_label": pct_label,
                    "amount": currency.round(b["amount"]),
                })
        return rows
