# -*- coding: utf-8 -*-
from odoo import _, models


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
