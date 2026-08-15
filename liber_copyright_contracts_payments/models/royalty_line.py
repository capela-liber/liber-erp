# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.tools import float_round


class EdlabContractRoyaltyLine(models.Model):
    _inherit = "edlab.contract.royalty.line"

    def _edlab_open_balance(self):
        """Return the royalties still owed on this line (positive = owed).

        The analytic account balance is negative while royalties are owed
        (accruals are booked negative, settlements positive). Payment-bill
        analytic lines are excluded so paying a bill does not, by itself, look
        like a fresh accrual: the period is settled through the last payment
        date instead.
        """
        self.ensure_one()
        account = self.analytic_account_id
        if not account:
            return 0.0
        groups = self.env["account.analytic.line"].sudo().read_group(
            [
                ("account_id", "=", account.id),
                ("edlab_is_royalty_payment", "!=", True),
            ],
            ["amount"],
            [],
        )
        balance = (groups[0]["amount"] or 0.0) if groups else 0.0
        return -balance

    def _edlab_has_open_payment_bill(self):
        """True if an uncancelled, not-yet-paid royalty bill already pays this
        line (avoids generating a duplicate bill before the first one is paid)."""
        self.ensure_one()
        return bool(
            self.env["account.move.line"].sudo().search_count(
                [
                    ("edlab_royalty_line_id", "=", self.id),
                    ("move_id.move_type", "=", "in_invoice"),
                    ("move_id.state", "!=", "cancel"),
                    (
                        "move_id.payment_state",
                        "in",
                        ("not_paid", "partial", "in_payment"),
                    ),
                ]
            )
        )

    def _edlab_advance_deduction(self, owed):
        """Portion of the recoupable advance netted out of what this bill
        pays: the open accruals minus the net owed. Zero when there is no
        advance left to recoup."""
        self.ensure_one()
        AnalyticLine = self.env["account.analytic.line"].sudo()
        domain = self._edlab_accrual_entry_domain()
        if self.last_payment_date:
            domain.append(("date", ">", self.last_payment_date))
        accrued = -sum(AnalyticLine.search(domain).mapped("amount"))
        return max(float_round(accrued - owed, precision_digits=2), 0.0)

    def _prepare_payment_bill_line_cmds(self, owed, company):
        """Bill lines paying this royalty line.

        When part of the royalties is eaten by the recoupable advance, the
        bill must SAY so: a gross royalties line plus a visible negative
        "advance recouped" line, instead of an opaque net total the author
        cannot reconcile with the statement."""
        self.ensure_one()
        deduction = self._edlab_advance_deduction(owed)
        if deduction <= 0:
            return [(0, 0, self._prepare_payment_bill_line_vals(owed, company))]
        gross = float_round(owed + deduction, precision_digits=2)
        main = self._prepare_payment_bill_line_vals(gross, company)
        recouped = self._prepare_payment_bill_line_vals(-deduction, company)
        recouped["name"] = _("Advance recouped %s - %s") % (
            self.contract_id.name or _("New"), self.product_id.display_name)
        return [(0, 0, main), (0, 0, recouped)]

    def _prepare_payment_bill_line_vals(self, amount, company):
        """Vendor bill line paying this royalty line: the configured product and
        the owed amount.

        The analytic account is deliberately NOT set on the bill line: paying
        the bill books a positive settlement entry on the analytic account (via
        the last-payment-date cutoff), which cleanly clears the open royalties.
        Adding the analytic here too would post a second, negative "cost" entry
        that leaves the analytic account's raw balance non-zero.
        """
        self.ensure_one()
        vals = {
            "product_id": company._contract_payment_product().id,
            "name": _("Royalties %s - %s")
            % (self.contract_id.name or _("New"), self.product_id.display_name),
            "quantity": 1.0,
            "price_unit": amount,
            "edlab_royalty_line_id": self.id,
            "tax_ids": [(6, 0, [])],
        }
        if company.contract_payment_account_id:
            vals["account_id"] = company.contract_payment_account_id.id
        return vals
