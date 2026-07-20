# -*- coding: utf-8 -*-
from odoo import fields, models


class EdlabContractRoyaltyLine(models.Model):
    _inherit = "edlab.contract.royalty.line"

    edlab_currency_id = fields.Many2one(
        related="contract_id.currency_id",
        string="Royalty Currency",
    )
    edlab_open_balance = fields.Monetary(
        string="Open Royalties",
        compute="_compute_edlab_open_balance",
        currency_field="edlab_currency_id",
        help="Royalties still owed on this line.",
    )

    def _compute_edlab_open_balance(self):
        for line in self:
            line.edlab_open_balance = (
                line._edlab_open_balance() if isinstance(line.id, int) else 0.0
            )
