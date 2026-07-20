# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    contract_tax_partner_id = fields.Many2one(
        "res.partner",
        string="Tax Authority",
        help="Government contact that receives the accumulated IRRF vendor "
        "bill. Withholding is only computed when this and the account below "
        "are set.",
    )
    contract_tax_account_id = fields.Many2one(
        "account.account",
        string="IRRF Liability Account",
        domain="[('company_ids', 'in', id)]",
        help="Liability account ('IRRF to pay') used both on the negative "
        "withholding line of the author's bill and on the government bill "
        "lines, so the liability is born at withholding and cleared when the "
        "tax is paid.",
    )
    contract_tax_journal_id = fields.Many2one(
        "account.journal",
        string="Tax Bill Journal",
        domain="[('type', '=', 'purchase'), ('company_id', '=', id)]",
        help="Purchase journal of the IRRF vendor bill. Empty = company "
        "default purchase journal.",
    )
    contract_tax_due_day = fields.Integer(
        string="Tax Due Day",
        default=20,
        help="Day of the following month when the withheld IRRF is due "
        "(DARF).",
    )
