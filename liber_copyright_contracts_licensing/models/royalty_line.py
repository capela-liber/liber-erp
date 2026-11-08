# -*- coding: utf-8 -*-
"""The author's share of rights-licensing invoices, booked as a royalty.

A licensing invoice is a customer invoice of the contract's company that
carries the contract on its header (``edlab_license_contract_id``) and, on
each line, the analytic account of the royalty line(s) it pays. Once that
invoice is PAID -- the same rule the sales follow -- each such line books
``-(line amount x licensing %)`` on the beneficiary's analytic account.

The entry is an ordinary accrual (it carries ``edlab_source_move_line_id``),
so everything downstream already counts it: the payment cutoff, the open
balance, the author's bill, the advance recoup, the IRRF and the statement
total. The extra marker ``edlab_license_royalty_line_id`` only tells the
statement which accruals belong in the Licensing section.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

PAID_STATES = ("paid", "in_payment")


def edlab_distribution_account_ids(move_line):
    """Analytic account ids named in a journal item's distribution.

    v19 keys a distribution by account ids joined with commas (one key per
    combination of plans), so a key is split before it is read."""
    ids = set()
    for key in (move_line.analytic_distribution or {}):
        ids.update(int(part) for part in str(key).split(",") if part)
    return ids


class EdlabContractRoyaltyLine(models.Model):
    _inherit = "edlab.contract.royalty.line"

    license_percentage = fields.Float(
        string="Licensing (%)",
        digits=(5, 2),
        help="Beneficiary's share of every rights-licensing invoice of this "
        "work, on the invoiced amount. Independent of the per-copy tiers. "
        "0 = licences pay this beneficiary nothing.",
    )

    @api.constrains("license_percentage")
    def _check_license_percentage(self):
        for line in self:
            if not 0.0 <= line.license_percentage <= 100.0:
                raise ValidationError(_(
                    "The licensing percentage must be between 0 and 100."))

    # ------------------------------------------------------------------
    # Booking
    # ------------------------------------------------------------------
    def _edlab_license_invoice_lines(self):
        """Product lines of the licensing invoices of these lines' contracts."""
        return self.env["account.move.line"].sudo().search([
            ("move_id.edlab_license_contract_id", "in", self.contract_id.ids),
            ("move_id.move_type", "=", "out_invoice"),
            ("display_type", "=", "product"),
        ])

    def _edlab_license_accrues(self, move_line):
        """Does this licensing invoice line owe this beneficiary a share now?

        Paid (posted and paid / in payment), within the contract term, naming
        this line's analytic account, with a percentage to apply. A reversed
        or cancelled invoice stops owing -- which is what lets a refunded
        licence come off the account before the author is paid."""
        self.ensure_one()
        move = move_line.move_id
        return bool(
            self.license_percentage
            and move.move_type == "out_invoice"
            and move.state == "posted"
            and move.payment_state in PAID_STATES
            and move.edlab_license_contract_id == self.contract_id
            and self.analytic_account_id.id in edlab_distribution_account_ids(move_line)
            and self.contract_id._edlab_in_term(move.invoice_date or move.date)
        )

    def _edlab_sync_license_accruals(self, invoice_lines=None):
        """Book (or unbook) the licensing accruals of these royalty lines.

        ``invoice_lines`` limits the sync to those licensing invoice lines
        (the payment hook passes the invoice just paid); by default every
        licensing line of the contracts is considered. Idempotent: one entry
        per (invoice line, royalty line). An entry whose invoice stopped
        owing is removed -- unless it is dated on or before the beneficiary's
        last payment, because then it was already paid out and is history.

        Returns ``(created, removed)``.
        """
        AnalyticLine = self.env["account.analytic.line"].sudo()
        royalties = self.filtered("analytic_account_id")
        if not royalties:
            return 0, 0
        if invoice_lines is None:
            invoice_lines = royalties._edlab_license_invoice_lines()
        invoice_lines = invoice_lines.filtered(
            lambda l: l.display_type == "product"
            and l.move_id.edlab_license_contract_id)
        if not invoice_lines:
            return 0, 0
        created = removed = 0
        existing_all = AnalyticLine.search([
            ("edlab_license_royalty_line_id", "in", royalties.ids),
            ("edlab_source_move_line_id", "in", invoice_lines.ids),
        ])
        for royalty in royalties:
            account = royalty.analytic_account_id
            existing = existing_all.filtered(
                lambda a: a.edlab_license_royalty_line_id == royalty)
            booked = existing.edlab_source_move_line_id
            due = invoice_lines.filtered(royalty._edlab_license_accrues)
            for line in due - booked:
                move = line.move_id
                # Company currency, whatever the invoice's: the analytic
                # account (and the author's bill) live in the contract's.
                base = -line.balance
                pct = royalty.license_percentage
                AnalyticLine.create({
                    "name": _("Licensing %(pct).2f%% - %(licensee)s",
                              pct=pct, licensee=move.partner_id.display_name),
                    "account_id": account.id,
                    "auto_account_id": account.id,
                    "date": move.invoice_date or move.date,
                    "amount": -(base * pct / 100.0),
                    # A licence sells no copies: keep the quantity out of
                    # every "copies sold" column.
                    "unit_amount": 0.0,
                    "partner_id": royalty.partner_id.id,
                    "product_id": line.product_id.id,
                    "company_id": royalty.company_id.id,
                    "edlab_royalty_percentage": pct,
                    "ref": move.name,
                    "edlab_source_move_line_id": line.id,
                    "edlab_license_royalty_line_id": royalty.id,
                })
                created += 1
            cutoff = royalty.last_payment_date
            stale = existing.filtered(
                lambda a: a.edlab_source_move_line_id not in due
                and not (cutoff and a.date <= cutoff))
            removed += len(stale)
            stale.unlink()
        return created, removed

    def _book_royalties_from_invoices(self, invoices):
        """Fill Royalty Lines books the licences too.

        Licences go FIRST so the payment cutoff the engine books afterwards
        already sees them. Licensing invoices are taken out of the sales
        pass: a licence billed with the work's own product would otherwise
        accrue twice, once at the tier and once at the licensing %."""
        created, removed = self._edlab_sync_license_accruals()
        res = super()._book_royalties_from_invoices(
            invoices.filtered(lambda m: not m.edlab_license_contract_id))
        if (created or removed) and isinstance(res, dict) \
                and res.get("tag") == "display_notification":
            params = res.setdefault("params", {})
            note = _("Licensing: %(created)s entr(ies) added, %(removed)s "
                     "removed.", created=created, removed=removed)
            params["message"] = "%s %s" % (note, params.get("message") or "")
            # Something WAS booked; the sales part of the message still says
            # what it could not do, but the run as a whole did work.
            params["type"] = "success"
        return res
