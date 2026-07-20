# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    edlab_contract_id = fields.Many2one(
        "edlab.contract",
        string="Copyright Contract",
        index=True,
        ondelete="set null",
        copy=False,
        help="Copyright contract this royalty payment bill was generated from.",
    )

    def _compute_amount(self):
        """After amounts/payment_state are computed, settle the royalties paid.

        ``payment_state`` is a stored field computed by ``_compute_amount`` in
        Odoo 15, so this is the reliable hook to react when a royalty payment
        bill becomes paid. For every royalty line the bill pays, stamp today as
        the last payment date and immediately book the settlement on its
        analytic account (a positive compensating entry that clears the open
        royalties up to that date) so the payment is reflected right away,
        without waiting for a manual "Fill Royalty Lines" run.
        """
        super()._compute_amount()
        today = fields.Date.context_today(self)
        for move in self:
            if move.move_type != "in_invoice":
                continue
            # A DRAFT bill has not paid anybody. It matters that this is checked:
            # a move that is still being built computes payment_state as "paid"
            # (nothing due yet = nothing owed), so without this guard the mere
            # act of generating the bill stamped a payment date on the royalty
            # line -- and the cutoff would then settle royalties nobody paid.
            if move.state != "posted":
                continue
            if move.payment_state not in ("paid", "in_payment"):
                continue
            royalty_lines = move.line_ids.mapped("edlab_royalty_line_id")
            to_update = royalty_lines.filtered(
                lambda r: not r.last_payment_date or r.last_payment_date < today
            )
            if to_update:
                to_update.sudo().write({"last_payment_date": today})
                # Empty invoices: only the last-payment-date cutoff runs, which
                # books the positive settlement that clears the open royalties.
                to_update.sudo()._book_royalties_from_invoices(
                    self.env["account.move"]
                )
