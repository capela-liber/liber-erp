# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class EdlabContract(models.Model):
    _inherit = "edlab.contract"

    edlab_bill_ids = fields.One2many(
        "account.move",
        "edlab_contract_id",
        string="Royalty Bills",
    )
    edlab_bill_count = fields.Integer(
        string="Royalty Bills",
        compute="_compute_edlab_bill_count",
    )
    edlab_bill_to_pay_count = fields.Integer(
        string="Bills to Pay",
        compute="_compute_edlab_bill_count",
    )
    edlab_bill_paid_count = fields.Integer(
        string="Paid Bills",
        compute="_compute_edlab_bill_count",
    )
    edlab_royalty_paid = fields.Monetary(
        string="Paid Royalties",
        compute="_compute_edlab_royalty_paid",
        currency_field="currency_id",
        help="Royalties already settled on this contract's beneficiaries' "
        "analytic accounts (the positive settlement entries booked when their "
        "payment bills were paid).",
    )

    @api.depends("royalty_line_ids.analytic_account_id")
    def _compute_edlab_royalty_paid(self):
        AnalyticLine = self.env["account.analytic.line"]
        for contract in self:
            accounts = contract.royalty_line_ids.analytic_account_id
            total = 0.0
            if accounts:
                groups = AnalyticLine.sudo().read_group(
                    [
                        ("account_id", "in", accounts.ids),
                        ("edlab_is_royalty_payment", "!=", True),
                        ("amount", ">", 0),
                    ],
                    ["amount"],
                    [],
                )
                total = (groups[0]["amount"] or 0.0) if groups else 0.0
            contract.edlab_royalty_paid = total

    @api.depends("edlab_bill_ids.state", "edlab_bill_ids.payment_state")
    def _compute_edlab_bill_count(self):
        Move = self.env["account.move"].sudo()
        for contract in self:
            base = [("edlab_contract_id", "=", contract.id), ("state", "!=", "cancel")]
            contract.edlab_bill_count = Move.search_count(base)
            contract.edlab_bill_to_pay_count = Move.search_count(
                base + [("payment_state", "in", ("not_paid", "partial"))]
            )
            contract.edlab_bill_paid_count = Move.search_count(
                base + [("payment_state", "in", ("paid", "in_payment"))]
            )

    def _action_view_royalty_bills(self, name, extra_domain):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "account.move",
            "domain": [("edlab_contract_id", "=", self.id)] + extra_domain,
            "view_mode": "list,form",
            "context": {
                "create": False,
                "default_move_type": "in_invoice",
                "default_edlab_contract_id": self.id,
            },
        }

    def action_view_royalty_bills(self):
        """All royalty payment bills of this contract."""
        return self._action_view_royalty_bills(
            _("Royalty Bills"), [("state", "!=", "cancel")]
        )

    def action_view_bills_to_pay(self):
        """Royalty bills of this contract still to be paid."""
        return self._action_view_royalty_bills(
            _("Bills to Pay"),
            [("state", "!=", "cancel"), ("payment_state", "in", ("not_paid", "partial"))],
        )

    def action_view_bills_paid(self):
        """Paid royalty bills of this contract."""
        return self._action_view_royalty_bills(
            _("Paid Bills"), [("payment_state", "in", ("paid", "in_payment"))]
        )

    @api.depends("royalty_line_ids.analytic_account_id")
    def _compute_edlab_royalty_balance(self):
        """Open royalties owed, excluding payment-bill analytic lines.

        Overrides the analytics layer so the actual cash cost booked by a
        royalty payment bill (a negative analytic line) does not re-inflate the
        owed balance; paid periods are settled through the last payment date.
        """
        AnalyticLine = self.env["account.analytic.line"]
        for contract in self:
            accounts = contract.royalty_line_ids.analytic_account_id
            total = 0.0
            if accounts:
                groups = AnalyticLine.sudo().read_group(
                    [
                        ("account_id", "in", accounts.ids),
                        ("edlab_is_royalty_payment", "!=", True),
                    ],
                    ["amount"],
                    [],
                )
                total = (groups[0]["amount"] or 0.0) if groups else 0.0
            contract.edlab_royalty_balance = total

    def action_generate_royalty_bills(self):
        """Generate vendor bills to pay the authors from the open royalties.

        One bill per beneficiary, one line per work whose analytic account still
        owes royalties (and has no open bill yet). Works for one or several
        contracts (e.g. from the list view Action menu). Returns an action
        listing the created bills.
        """
        company = self.company_id[:1] or self.env.company
        # Only reachable when the default "Royalties" product was deleted AND the
        # company has no product of its own: the fallback covers the normal case.
        if not company._contract_payment_product():
            raise UserError(
                _(
                    "The bill lines that pay authors need a product, and neither "
                    "%s nor this module has one: the default \"Royalties\" product "
                    "is gone. Set one under Settings > Users & Companies > "
                    "Companies > %s > Copyrights > Beneficiary Payments > Payment "
                    "Product.",
                    company.display_name, company.display_name,
                )
            )
        Move = self.env["account.move"]
        created = Move.browse()
        for contract in self:
            company = contract.company_id or self.env.company
            grouped = {}
            for line in contract.royalty_line_ids:
                if not line.analytic_account_id:
                    continue
                if line._edlab_has_open_payment_bill():
                    continue
                owed = line._edlab_open_balance()
                if float_compare(owed, 0.0, precision_digits=2) <= 0:
                    continue
                grouped.setdefault(line.partner_id, []).append((line, owed))
            for partner, items in grouped.items():
                vals = contract._prepare_royalty_bill_vals(partner, items, company)
                created |= Move.sudo().with_company(company).create(vals)
        if not created:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Royalty bills"),
                    "message": _(
                        "No bills to create - the beneficiaries have no open "
                        "royalties, or their bills already exist."
                    ),
                    "type": "info",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Royalty Bills"),
            "res_model": "account.move",
            "domain": [("id", "in", created.ids)],
            "view_mode": "list,form",
            "context": {"create": False, "default_move_type": "in_invoice"},
        }

    def _prepare_royalty_bill_vals(self, partner, items, company):
        """Header values for a beneficiary's royalty payment vendor bill."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        due = today + relativedelta(days=company.contract_payment_days or 0)
        line_cmds = [
            (0, 0, line._prepare_payment_bill_line_vals(owed, company))
            for line, owed in items
        ]
        vals = {
            "move_type": "in_invoice",
            "partner_id": partner.id,
            "invoice_date": today,
            "invoice_date_due": due,
            "company_id": company.id,
            "currency_id": (self.currency_id or company.currency_id).id,
            "invoice_origin": self.name,
            # Bill Reference: contract number + beneficiary. Odoo enforces a
            # unique vendor reference per commercial partner, and several
            # beneficiaries can share one parent company, so the plain contract
            # number would clash; the beneficiary keeps it unique and readable.
            "ref": "%s · %s" % (self.name, partner.name),
            "edlab_contract_id": self.id,
            "invoice_line_ids": line_cmds,
        }
        if company.contract_payment_journal_id:
            vals["journal_id"] = company.contract_payment_journal_id.id
        return vals
