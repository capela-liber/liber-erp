# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Deliberately NOT the payments module's edlab_royalty_line_id: that field
    # marks lines that PAY a royalty line and feeds its open-bill check;
    # intercompany lines carrying it would block author bill generation.
    edlab_interco_royalty_line_id = fields.Many2one(
        "edlab.contract.royalty.line",
        string="Intercompany Royalty Line",
        index=True,
        ondelete="set null",
        copy=False,
        help="Royalty line (contract x work x beneficiary) whose "
        "cross-company accruals this intercompany invoice line charges.",
    )
