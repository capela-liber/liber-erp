# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    edlab_agency = fields.Char(
        string="Agency",
        help="Bank branch (agência) printed on the royalty statement.",
    )
