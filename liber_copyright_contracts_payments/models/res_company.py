# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    contract_payment_product_id = fields.Many2one(
        "product.product",
        string="Payment Product",
        help="Product placed on the vendor bill lines generated to pay authors. "
        "Leave empty to use the \"Royalties\" service product shipped with this "
        "module.",
    )

    def _contract_payment_product(self):
        """The product the royalty bill lines carry.

        Falls back to the module's own "Royalties" service product when the
        company has not chosen one. Without the fallback, the feature is dead on
        arrival on every database until someone finds the setting -- and the
        setting is a preference, not a prerequisite.
        """
        self.ensure_one()
        if self.contract_payment_product_id:
            return self.contract_payment_product_id
        template = self.env.ref(
            "liber_copyright_contracts_payments.product_royalty_payment",
            raise_if_not_found=False)
        return template.product_variant_id if template else self.env["product.product"]
    contract_payment_account_id = fields.Many2one(
        "account.account",
        string="Payment Account",
        domain="[('company_ids', 'in', id)]",
        help="Expense account used on the vendor bill lines that pay royalties. "
        "Leave empty to use the product's default expense account.",
    )
    contract_payment_journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type', '=', 'purchase'), ('company_id', '=', id)]",
        help="Purchase journal used for the royalty payment vendor bills. "
        "Leave empty to use the company default purchase journal.",
    )
    contract_payment_days = fields.Integer(
        string="Due in (days)",
        default=30,
        help="Number of days added to today to set the due date of the royalty "
        "payment vendor bills.",
    )
