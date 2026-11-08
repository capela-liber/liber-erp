# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    edlab_license_contract_id = fields.Many2one(
        "edlab.contract",
        string="Licensed Contract",
        index=True,
        ondelete="restrict",
        copy=True,
        help="Copyright contract whose rights this customer invoice licenses. "
        "When the invoice is paid, each beneficiary named on its lines (by "
        "analytic account) is owed their licensing percentage of the line.",
    )

    @api.model
    def default_get(self, fields_list):
        """A new licensing invoice lands in the contract's company, by its
        licensing journal. The lines come from the onchange below."""
        res = super().default_get(fields_list)
        contract = self.env["edlab.contract"].browse(
            res.get("edlab_license_contract_id")).exists()
        if not contract or res.get("move_type") not in ("out_invoice", "out_refund"):
            return res
        journal = contract.company_id._contract_license_journal()
        if journal and "journal_id" in fields_list:
            res["journal_id"] = journal.id
        return res

    @api.onchange("edlab_license_contract_id")
    def _onchange_edlab_license_contract_id(self):
        """The licensing product and account, and the beneficiaries' analytic
        accounts, on a fresh line: only the licensee and the amount are left
        to type. Runs on the form's first onchange, when the contract comes
        as a default. Not in ``default_get``: there the lines exist before
        the invoice has a company, and pricing the product needs one.
        Never touches an invoice that already has lines."""
        if (self.edlab_license_contract_id and not self.invoice_line_ids
                and self.move_type in ("out_invoice", "out_refund")):
            self.invoice_line_ids = \
                self.edlab_license_contract_id._edlab_license_line_commands()

    @api.constrains("edlab_license_contract_id", "company_id")
    def _check_license_contract_company(self):
        for move in self:
            contract = move.edlab_license_contract_id
            if contract and contract.company_id != move.company_id:
                raise ValidationError(_(
                    "A licensing invoice belongs to the company that holds the "
                    "rights: contract %(contract)s is %(company)s's, the invoice "
                    "is %(move_company)s's.",
                    contract=contract.name,
                    company=contract.company_id.display_name,
                    move_company=move.company_id.display_name))

    def _compute_payment_state(self):
        """A licensing invoice that becomes paid owes the author right away.

        Sales wait for Fill Royalty Lines; a licence is one invoice the user
        just issued from the contract, and "paid, but the author's account
        does not show it" would read as a bug. The sync is idempotent and runs
        the other way too: an invoice that stops being paid (reset, reversed)
        takes its unpaid-out share off the account."""
        super()._compute_payment_state()
        licences = self.filtered(
            lambda m: m.edlab_license_contract_id and m.move_type == "out_invoice"
            and isinstance(m.id, int))
        if not licences:
            return
        royalties = licences.edlab_license_contract_id.royalty_line_ids.sudo()
        royalties._edlab_sync_license_accruals(
            licences.sudo().invoice_line_ids)
