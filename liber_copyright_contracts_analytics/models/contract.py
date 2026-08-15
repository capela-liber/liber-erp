# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class EdlabContract(models.Model):
    _inherit = "edlab.contract"

    edlab_royalty_balance = fields.Monetary(
        string="Open Royalties",
        compute="_compute_edlab_royalty_balance",
        currency_field="currency_id",
        help="Sum of the analytic balances of this contract's beneficiaries: "
        "the royalties still owed (paid periods are settled by the cutoff "
        "compensations, so they no longer count here).",
    )

    special_sales_count = fields.Integer(
        string="Special Sales",
        compute="_compute_special_sales_count",
    )

    # The analytic accounts belong to THIS layer, not to the payments one that
    # happened to draw the smart buttons: a database with analytics and no
    # payments module still has analytic accounts to count and to open.
    edlab_analytic_count = fields.Integer(
        string="Analytic Accounts",
        compute="_compute_edlab_analytic_count",
    )

    # partner_ids (the beneficiaries) is computed and stored by the base
    # module; this is just its size, for the stat button.
    beneficiary_count = fields.Integer(
        string="Beneficiary Count",
        compute="_compute_beneficiary_count",
    )

    def _special_sales_domain(self):
        """Special-sale customer invoices selling one of this contract's works."""
        self.ensure_one()
        base = self.company_id._special_sales_domain()
        if ("id", "=", False) in base or not self.product_ids:
            return [("id", "=", False)]
        return base + [
            ("invoice_line_ids.product_id.product_tmpl_id", "in", self.product_ids.ids)
        ]

    @api.depends(
        "product_ids",
        "company_id.contract_special_sales_team_ids",
        "company_id.contract_special_min_discount",
    )
    def _compute_special_sales_count(self):
        Move = self.env["account.move"].sudo()
        for contract in self:
            contract.special_sales_count = Move.search_count(
                contract._special_sales_domain()
            )

    def action_view_special_sales(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Special Sales"),
            "res_model": "account.move",
            "domain": self._special_sales_domain(),
            "view_mode": "list,form",
            "context": {"create": False},
        }

    @api.depends("royalty_line_ids.analytic_account_id")
    def _compute_edlab_royalty_balance(self):
        AnalyticLine = self.env["account.analytic.line"]
        for contract in self:
            accounts = contract.royalty_line_ids.analytic_account_id
            total = 0.0
            if accounts:
                groups = AnalyticLine.sudo().read_group(
                    [("account_id", "in", accounts.ids)], ["amount"], []
                )
                total = (groups[0]["amount"] or 0.0) if groups else 0.0
            contract.edlab_royalty_balance = total

    def action_open_analytic_wizard(self):
        """Open a popup listing every beneficiary to create/sync analytic accounts.

        Works for one or several contracts (e.g. when triggered from the list
        view Action menu), aggregating the royalty lines of every record.
        """
        line_vals = [
            (0, 0, {
                "royalty_line_id": line.id,
                "analytic_account_id": line.analytic_account_id.id,
                "to_apply": not line.analytic_account_id,
            })
            for line in self.mapped("royalty_line_ids")
        ]
        wizard = self.env["edlab.contract.analytic.wizard"].create({
            "contract_id": self[:1].id,
            "line_ids": line_vals,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Analytic Accounts"),
            "res_model": "edlab.contract.analytic.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.depends("royalty_line_ids.analytic_account_id")
    def _compute_edlab_analytic_count(self):
        for contract in self:
            contract.edlab_analytic_count = len(
                contract.royalty_line_ids.analytic_account_id
            )

    def action_view_contract_analytics(self):
        """Open the analytic accounts of this contract's beneficiaries/works.

        The usual contract has exactly ONE analytic account, and a list of one
        is a detour: the button promises "take me to the analytic", so a single
        account opens straight on its form. Several open as a list.
        """
        self.ensure_one()
        accounts = self.royalty_line_ids.analytic_account_id
        action = {
            "type": "ir.actions.act_window",
            "name": _("Contract Analytics"),
            "res_model": "account.analytic.account",
            "context": {"create": False},
        }
        if len(accounts) == 1:
            action.update({"res_id": accounts.id, "view_mode": "form"})
        else:
            action.update({
                "domain": [("id", "in", accounts.ids)],
                "view_mode": "list,form",
            })
        return action

    @api.depends("partner_ids")
    def _compute_beneficiary_count(self):
        for contract in self:
            contract.beneficiary_count = len(contract.partner_ids)

    def action_view_contract_beneficiaries(self):
        """Open this contract's beneficiaries (the partners of its royalty
        lines). Same rule as the analytics button: one beneficiary goes
        straight to their card, several open as a list."""
        self.ensure_one()
        partners = self.partner_ids
        action = {
            "type": "ir.actions.act_window",
            "name": _("Beneficiaries"),
            "res_model": "res.partner",
            "context": {"create": False},
        }
        if len(partners) == 1:
            action.update({"res_id": partners.id, "view_mode": "form"})
        else:
            action.update({
                "domain": [("id", "in", partners.ids)],
                "view_mode": "list,form",
            })
        return action

    def _edlab_in_term(self, day):
        """Was this contract in force on `day`?

        Royalties accrue on the sales made while the contract was alive. A sale
        invoiced after the expiration date is not covered by it -- that is what
        stops an expired contract from taking new entries, while leaving intact
        everything it legitimately earned before expiring.

        A cancelled contract covers nothing at all: cancelling is not the same as
        letting a term run out, and there is no date to bound it by.
        """
        self.ensure_one()
        if not day:
            return False
        if self.state == "cancelled":
            return False
        if self.signature_date and day < self.signature_date:
            return False
        if self.expiration_date and day > self.expiration_date:
            return False
        return True

    def _edlab_royalty_invoice_domain(self):
        """Domain of the customer invoices whose sales feed this contract's
        royalty accrual. Extension hook: the intercompany layer restricts it
        to the contract company plus its configured source companies."""
        self.ensure_one()
        return [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("paid", "in_payment", "reversed")),
        ]

    def action_fill_royalty_lines(self):
        """Fill the contract's analytic accounts with royalty lines.

        Books the royalty owed on each beneficiary's analytic account from all
        paid customer invoices of the contract's works. Idempotent.
        """
        royalty_lines = self.mapped("royalty_line_ids").filtered(
            lambda line: line.analytic_account_id
        )
        Move = self.env["account.move"].sudo()
        # The domain may differ per contract (per company, really), so search
        # once per distinct domain instead of once per contract.
        domains = {}
        for contract in self:
            domain = contract._edlab_royalty_invoice_domain()
            domains.setdefault(repr(domain), domain)
        invoices = Move.browse()
        for domain in domains.values():
            invoices |= Move.search(domain)
        return royalty_lines._book_royalties_from_invoices(invoices)
