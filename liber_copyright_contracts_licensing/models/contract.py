# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class EdlabContract(models.Model):
    _inherit = "edlab.contract"

    edlab_license_invoice_ids = fields.One2many(
        "account.move",
        "edlab_license_contract_id",
        string="Licensing Invoices",
    )
    edlab_license_count = fields.Integer(
        string="Licensing",
        compute="_compute_edlab_license_count",
    )

    @api.depends("edlab_license_invoice_ids")
    def _compute_edlab_license_count(self):
        Move = self.env["account.move"].sudo()
        for contract in self:
            contract.edlab_license_count = Move.search_count([
                ("edlab_license_contract_id", "=", contract.id),
                ("move_type", "in", ("out_invoice", "out_refund")),
                ("state", "!=", "cancel"),
            ]) if isinstance(contract.id, int) else 0

    def action_view_license_invoices(self):
        """The contract's licensing invoices, and where new ones are made.

        No wizard: the list's own *New* button is the way in. The context only
        names the contract; the invoice's defaults (journal of the contract's
        company, licensing product, account and the beneficiaries' analytic
        accounts) come from ``account.move.default_get``. Putting them in the
        context instead would leak ``default_journal_id`` into every popup
        opened from the invoice -- the payment wizard first of all."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Licensing - %s", self.name),
            "res_model": "account.move",
            "domain": [
                ("edlab_license_contract_id", "=", self.id),
                ("move_type", "in", ("out_invoice", "out_refund")),
            ],
            "views": [
                (self.env.ref("account.view_out_invoice_tree").id, "list"),
                (self.env.ref("account.view_move_form").id, "form"),
            ],
            "context": {
                "default_move_type": "out_invoice",
                "default_edlab_license_contract_id": self.id,
            },
        }

    def _edlab_license_line_commands(self):
        """Default lines of a new licensing invoice: one per WORK.

        Each line names every beneficiary of that work (their analytic
        accounts at 100%): a licence of the work is one amount, and each
        beneficiary takes their own licensing % of all of it. Two heirs at
        20% each on a R$ 1.000 licence are owed R$ 200 apiece -- splitting
        the line between them would halve what each one is owed.

        Only the product and the work are set here; the income account and
        the analytic distribution follow from them in the line's computes
        (see account_move_line.py), so they survive a form that does not
        show the analytic column."""
        self.ensure_one()
        product = self.company_id._contract_license_product()
        commands = []
        works = self.royalty_line_ids.filtered("analytic_account_id").product_id
        for work in works:
            vals = {
                "name": _("Licensing of %(work)s (contract %(contract)s)",
                          work=work.display_name, contract=self.name),
                "quantity": 1.0,
                "edlab_license_work_id": work.id,
            }
            if product:
                vals["product_id"] = product.id
            commands.append((0, 0, vals))
        return commands
