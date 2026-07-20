# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    edlab_irrf_withholding = fields.Boolean(
        string="IRRF Withholding Line",
        copy=False,
        help="Set on the negative line of the author's bill that withholds "
        "the IRRF (payable becomes net).",
    )
    # Deliberately NOT reusing edlab_royalty_line_id here: that field marks
    # lines that PAY a royalty line and feeds _edlab_has_open_payment_bill;
    # tax bill lines carrying it would block new author bill generation.
    edlab_tax_source_move_id = fields.Many2one(
        "account.move",
        string="Tax Source Bill",
        index=True,
        ondelete="set null",
        copy=False,
        help="Author payment bill whose withheld IRRF this tax bill line "
        "carries.",
    )
    edlab_tax_royalty_line_id = fields.Many2one(
        "edlab.contract.royalty.line",
        string="Tax Royalty Line",
        index=True,
        ondelete="set null",
        copy=False,
        help="Royalty line (work x beneficiary) this tax bill line refers to.",
    )
