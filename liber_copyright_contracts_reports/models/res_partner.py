# -*- coding: utf-8 -*-
import babel.dates

from odoo import _, api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    edlab_royalty_line_ids = fields.One2many(
        "edlab.contract.royalty.line",
        "partner_id",
        string="Royalty Lines",
        help="Royalty lines (across all contracts) where this contact is the "
        "beneficiary.",
    )
    is_edlab_author = fields.Boolean(
        string="Is Beneficiary",
        compute="_compute_is_edlab_author",
        store=True,
        help="True when this contact is the beneficiary of at least one "
        "royalty line.",
    )
    edlab_birthdate = fields.Date(string="Birth Date")
    edlab_rg = fields.Char(string="RG")
    edlab_pis = fields.Char(string="PIS")
    edlab_nationality = fields.Char(string="Nationality")
    edlab_irrf_percentage = fields.Float(
        string="IRRF (%)",
        digits=(5, 2),
        help="Withholding income tax percentage deducted from the royalty "
        "statement total. Leave 0 when no withholding applies.",
    )
    edlab_last_statement_date = fields.Date(
        string="Last Statement Sent",
        readonly=True,
        copy=False,
        help="End date of the period covered by the last royalty statement "
        "emailed to this author.",
    )
    edlab_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_edlab_royalty_balance",
        string="Royalty Currency",
    )
    edlab_royalty_balance = fields.Monetary(
        string="Open Royalties",
        compute="_compute_edlab_royalty_balance",
        currency_field="edlab_currency_id",
        help="Royalties still owed to this author, all contracts combined.",
    )

    @api.depends("edlab_royalty_line_ids")
    def _compute_is_edlab_author(self):
        for partner in self:
            partner.is_edlab_author = bool(partner.edlab_royalty_line_ids)

    def _compute_edlab_royalty_balance(self):
        for partner in self:
            partner.edlab_currency_id = self.env.company.currency_id
            partner.edlab_royalty_balance = sum(
                line._edlab_open_balance()
                for line in partner.edlab_royalty_line_ids
                if isinstance(line.id, int)
            )

    def action_open_royalty_statement_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Royalty Statement"),
            "res_model": "edlab.royalty.statement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_ids": [(6, 0, self.ids)]},
        }

    # ------------------------------------------------------------------
    # Statement data (used by the QWeb report and the sending wizard)
    # ------------------------------------------------------------------
    def _edlab_statement_date_label(self, value):
        """'15 de setembro de 2025' — pt-BR regardless of the user/partner
        language: the statement is a Brazilian document with fixed pt-BR
        labels, so its dates must match even on databases without pt_BR."""
        return babel.dates.format_date(
            value, format="d 'de' MMMM 'de' y", locale="pt_BR"
        )

    def _edlab_open_payment_bills(self):
        """The author's open royalty payment bills (one row per bill).

        A bill is open when it is an uncancelled vendor bill (``in_invoice``)
        still owing money (``not_paid``/``partial``/``in_payment``) and at least
        one of its lines pays a royalty line belonging to this author. Its
        residual is what the author is still owed through that bill, so it should
        match the statement total."""
        self.ensure_one()
        line_ids = self.edlab_royalty_line_ids.ids
        if not line_ids:
            return []
        bill_lines = self.env["account.move.line"].sudo().search(
            [
                ("edlab_royalty_line_id", "in", line_ids),
                ("move_id.move_type", "=", "in_invoice"),
                ("move_id.state", "!=", "cancel"),
                ("move_id.payment_state", "in", ("not_paid", "partial", "in_payment")),
            ]
        )
        state_labels = {
            "not_paid": _("open"),
            "partial": _("partially paid"),
            "in_payment": _("in payment"),
        }
        bills = []
        for move in bill_lines.mapped("move_id").sorted(
            key=lambda m: (m.invoice_date or m.date, m.name or "")
        ):
            # The bills listed here are the OPEN ones, so the payment date the
            # author cares about is the one they will be paid ON: the due date.
            # A bill already settled never reaches this list at all.
            due = move.invoice_date_due
            bills.append(
                {
                    "name": move.name,
                    "date": move.invoice_date or move.date,
                    "date_label": self._edlab_statement_date_label(
                        move.invoice_date or move.date
                    ),
                    "due_date": due,
                    "due_label": self._edlab_statement_date_label(due) if due else "",
                    "amount_total": move.amount_total,
                    "amount_residual": move.amount_residual,
                    "state_label": state_labels.get(
                        move.payment_state, move.payment_state or ""
                    ),
                }
            )
        return bills

    def _edlab_special_sales_rows(self, date_from, date_to):
        """Detailed special sales of this beneficiary's works in the period.

        A special sale is a discounted invoice from a configured special sales
        team (see the company settings); this reuses the beneficiary's
        ``_special_sales_domain`` so the rows match exactly what the "Special
        Sales" figures count, then drills into the qualifying invoice lines.
        One row per line: customer, invoice, work, copies, discount and net
        amount. ``date_from`` is optional (None => from the beginning)."""
        self.ensure_one()
        domain = self._special_sales_domain()
        if ("id", "=", False) in domain:
            return []
        if date_from:
            domain = domain + [("invoice_date", ">=", date_from)]
        if date_to:
            domain = domain + [("invoice_date", "<=", date_to)]
        moves = self.env["account.move"].sudo().search(
            domain, order="invoice_date, name"
        )
        works = (
            self.env["edlab.contract.royalty.line"]
            .sudo()
            .search([("partner_id", "=", self.id)])
            .product_id
        )
        min_discount = self.env.company.contract_special_min_discount
        rows = []
        for move in moves:
            for line in move.invoice_line_ids:
                if line.product_id.product_tmpl_id not in works:
                    continue
                if line.discount < min_discount:
                    continue
                qty = line.quantity
                rows.append(
                    {
                        "customer": move.partner_id.display_name,
                        "invoice": move.name,
                        "work": line.product_id.display_name,
                        "qty": int(qty) if qty == int(qty) else qty,
                        "discount_label": ("%.2f" % line.discount).replace(".", ",")
                        + "%",
                        "amount": line.price_subtotal,
                    }
                )
        return rows

    def _edlab_royalty_statement(self, date_to=None):
        """Aggregate this author's royalties still open, tied to the bill.

        ``date_to`` is the end of the covered period (defaults to today). The
        statement covers, per royalty line, everything accrued **since that
        line's last payment** (or from the very beginning when it was never
        paid) up to ``date_to``. The last payment date
        settles every accrual up to it (via the analytic cutoff entry), so the
        remaining accruals are exactly the open balance -- which is exactly what
        an open payment bill contains. The statement total therefore equals
        ``_edlab_open_balance()`` and matches the bill(s) reported below.

        One row per royalty line (work/channel) with an open balance, across all
        the author's contracts: copies sold, base amount, royalty percentage (or
        "variable" when tiers changed) and the royalty owed.
        """
        self.ensure_one()
        AnalyticLine = self.env["account.analytic.line"].sudo()
        currency = self.env.company.currency_id
        today = fields.Date.context_today(self)
        date_to = date_to or today
        rows = []
        total = 0.0
        recouped = 0.0
        # Earliest last-payment date across the lines that carry an open balance,
        # used to label the period. Stays None (=> "since the beginning") as soon
        # as one such line was never paid, since its numbers go back to the start.
        period_start = None
        period_from_beginning = False
        for line in self.edlab_royalty_line_ids.sorted(
            key=lambda l: (l.contract_id.name or "", l.product_id.display_name or "")
        ):
            account = line.analytic_account_id
            if not account:
                continue
            cutoff = line.last_payment_date
            # Accrual entries (extension hook: includes e.g. audit residuals)
            domain = line._edlab_accrual_entry_domain()
            # Only accruals dated after the last payment remain open; without a
            # payment, everything from the start is open. Bounded above by the
            # period end (with date_to = today, the sum equals the analytic open
            # balance and hence the bill).
            if cutoff:
                domain.append(("date", ">", cutoff))
            domain.append(("date", "<=", date_to))
            entries = AnalyticLine.search(domain)
            if not entries:
                continue
            if cutoff:
                if period_start is None or cutoff < period_start:
                    period_start = cutoff
            else:
                period_from_beginning = True
            qty = sum(entries.mapped("unit_amount"))
            amount = -sum(entries.mapped("amount"))
            base = sum(
                -entry.amount * 100.0 / entry.edlab_royalty_percentage
                for entry in entries
                if entry.edlab_royalty_percentage
            )
            percentages = sorted(set(entries.mapped("edlab_royalty_percentage")))
            if len(percentages) == 1:
                pct_label = ("%.2f" % percentages[0]).replace(".", ",") + "%"
            else:
                pct_label = _("variable")
            rows.append(
                {
                    "line": line,
                    "work": line.product_id.display_name,
                    "contract": line.contract_id.name,
                    "qty": int(qty) if qty == int(qty) else qty,
                    "base": currency.round(base),
                    "percentage_label": pct_label,
                    "amount": currency.round(amount),
                }
            )
            total += amount
            # The recoupable advance is money ALREADY PAID to the author, and it
            # is recovered as the royalties accrue: the bill deducts it (it lives
            # on the analytic account, so _edlab_open_balance nets it out). The
            # statement was summing accruals only, so it promised the author more
            # than the bill would pay -- the two numbers have to be the same one.
            advance_domain = [
                ("account_id", "=", account.id),
                ("edlab_advance_line_id", "!=", False),
                ("date", "<=", date_to),
            ]
            if cutoff:
                # An advance already settled by a past payment is not recouped
                # twice: the cutoff entry closed everything up to that date.
                advance_domain.append(("date", ">", cutoff))
            recouped += sum(AnalyticLine.search(advance_domain).mapped("amount"))
        accrued = currency.round(total)
        # Cannot recover more than what was earned: the leftover stays to be
        # recouped against future royalties.
        recouped = currency.round(min(recouped, accrued))
        total = currency.round(accrued - recouped)
        irrf_pct = self.edlab_irrf_percentage or 0.0
        irrf = currency.round(total * irrf_pct / 100.0)
        bank = self.bank_ids[:1]
        address = ", ".join(
            part.strip()
            for part in (self.contact_address or "").split("\n")
            if part.strip()
        )
        # Period label: from the last payment (or the beginning) up to date_to.
        date_from = None if period_from_beginning else period_start
        today_label = self._edlab_statement_date_label(today)
        date_to_label = self._edlab_statement_date_label(date_to)
        if date_from:
            period_label = "%s\N{EN DASH}%s" % (
                self._edlab_statement_date_label(date_from),
                date_to_label,
            )
        else:
            period_label = _("since the beginning \N{EN DASH}%s") % date_to_label
        bills = self._edlab_open_payment_bills()
        special_sales = self._edlab_special_sales_rows(date_from, date_to)
        special_sales_total = currency.round(
            sum(row["amount"] for row in special_sales)
        )
        works = list(dict.fromkeys(row["work"] for row in rows))
        # Advances paid to the beneficiary (per work), declared when any exists.
        advance_lines = self.edlab_royalty_line_ids.filtered(
            lambda l: l.recoupable_advance or l.non_recoupable_advance
        ).sorted(
            key=lambda l: (l.contract_id.name or "", l.product_id.display_name or "")
        )
        advances = [
            {
                "work": line.product_id.display_name,
                "contract": line.contract_id.name,
                "recoupable": currency.round(line.recoupable_advance),
                "non_recoupable": currency.round(line.non_recoupable_advance),
            }
            for line in advance_lines
        ]
        recoupable_advance_total = currency.round(
            sum(a["recoupable"] for a in advances)
        )
        non_recoupable_advance_total = currency.round(
            sum(a["non_recoupable"] for a in advances)
        )
        return {
            "partner": self,
            "date_from": date_from,
            "date_to": date_to,
            "period_label": period_label,
            "today_label": today_label,
            "bills": bills,
            "special_sales": special_sales,
            "special_sales_total": special_sales_total,
            "advances": advances,
            "recoupable_advance_total": recoupable_advance_total,
            "non_recoupable_advance_total": non_recoupable_advance_total,
            "works": works,
            "works_label": ", ".join(works),
            "address": address,
            "bank": bank,
            "rows": rows,
            # `accrued` is what the works earned; `total` is what is actually
            # payable (accrued minus the advance recovered in this period), and
            # it is the number the bill is built from. Keeping both apart is what
            # lets the statement show the author WHY the two differ.
            "accrued": accrued,
            "advance_recouped": recouped,
            "total": total,
            "irrf_pct": irrf_pct,
            "irrf": irrf,
            "net": currency.round(total - irrf),
            "currency": currency,
        }
