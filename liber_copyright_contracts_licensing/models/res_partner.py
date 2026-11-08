# -*- coding: utf-8 -*-
"""The statement shows licences in their own section.

Licensing accruals are accruals: the statement total, the bill, the advance
recoup and the IRRF already include them, and none of that is touched here.
What changes is the breakdown: the royalties table is "copies sold x base x
%", and a licence has no copies -- folded into the work's row it would bend
the base and turn the percentage into "variable". So it is taken out of the
row and listed apart, one line per licence: date, licensee, base, %, share.
"""
from odoo import _, fields, models

from odoo.addons.liber_copyright_contracts_reports.models.res_partner import (
    edlab_work_label,
)


def _pct_label(percentages):
    if len(percentages) == 1:
        return ("%.2f" % percentages[0]).replace(".", ",") + "%"
    return _("variable")


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _edlab_royalty_statement(self, date_to=None):
        res = super()._edlab_royalty_statement(date_to=date_to)
        currency = res["currency"]
        AnalyticLine = self.env["account.analytic.line"].sudo()
        date_to = res.get("date_to") or fields.Date.context_today(self)
        licensing = []
        rows = []
        for row in res["rows"]:
            line = row["line"]
            window = [("date", "<=", date_to)]
            if line.last_payment_date:
                window.append(("date", ">", line.last_payment_date))
            licences = AnalyticLine.search(
                [("edlab_license_royalty_line_id", "=", line.id)] + window,
                order="date, id")
            if not licences:
                rows.append(row)
                continue
            for entry in licences:
                source = entry.edlab_source_move_line_id
                pct = entry.edlab_royalty_percentage
                licensing.append({
                    "line": line,
                    "date": entry.date,
                    "date_label": entry.date.strftime("%d/%m/%Y"),
                    "work": edlab_work_label(line.product_id),
                    "contract": line.contract_id.name,
                    "licensee": source.move_id.partner_id.display_name or "",
                    "invoice": source.move_id.name or "",
                    "description": source.name or "",
                    "base": currency.round(-entry.amount * 100.0 / pct) if pct else 0.0,
                    "percentage_label": _pct_label([pct]),
                    "amount": currency.round(-entry.amount),
                })
            # What is left of the row is the sales part: rebuild it from the
            # accruals that are NOT licences, with the same arithmetic as the
            # reports layer, so the row still reads "copies x base x %".
            sales = AnalyticLine.search(
                line._edlab_accrual_entry_domain() + window
                + [("edlab_license_royalty_line_id", "=", False)])
            if not sales:
                continue
            qty = sum(sales.mapped("unit_amount"))
            row = dict(row)
            row.update({
                "qty": int(qty) if qty == int(qty) else qty,
                "base": currency.round(sum(
                    -e.amount * 100.0 / e.edlab_royalty_percentage
                    for e in sales if e.edlab_royalty_percentage)),
                "percentage_label": _pct_label(
                    sorted(set(sales.mapped("edlab_royalty_percentage")))),
                "amount": currency.round(-sum(sales.mapped("amount"))),
            })
            rows.append(row)
        res["rows"] = rows
        res["licensing"] = licensing
        res["licensing_total"] = currency.round(sum(r["amount"] for r in licensing))
        # The royalties table's own footer: its rows no longer add up to the
        # whole accrued amount once the licences are listed apart.
        res["royalties_total"] = currency.round(sum(r["amount"] for r in rows))
        return res
