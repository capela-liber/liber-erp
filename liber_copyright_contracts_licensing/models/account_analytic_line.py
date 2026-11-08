# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    edlab_license_royalty_line_id = fields.Many2one(
        "edlab.contract.royalty.line",
        string="Licensing Of",
        index=True,
        ondelete="cascade",
        help="Set on the accrual that books a beneficiary's share of a paid "
        "rights-licensing invoice. The entry is an accrual like any royalty "
        "(it also carries the source invoice line); this marker is what lets "
        "the statement show it in its own section.",
    )
