# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    edlab_royalty_line_id = fields.Many2one(
        "edlab.contract.royalty.line",
        string="Royalty Line",
        index=True,
        ondelete="set null",
        copy=False,
        help="Royalty line (work x beneficiary) this vendor bill line pays. "
        "When the bill is paid, this royalty line's last payment date is "
        "updated.",
    )

    def _prepare_analytic_lines(self):
        """Stamp the payment marker on analytic lines born from royalty bills.

        The native analytic lines generated when a royalty payment bill line is
        posted must not inflate the 'Open Royalties' owed balance (it is a cash
        cost, not a new accrual), so tag them. v19: the hook is per move line
        (``_prepare_analytic_lines``); the v15 batch ``_prepare_analytic_line``
        no longer exists and an override of it is never called.
        """
        vals_list = super()._prepare_analytic_lines()
        if self.edlab_royalty_line_id:
            for vals in vals_list:
                vals["edlab_is_royalty_payment"] = True
        return vals_list
