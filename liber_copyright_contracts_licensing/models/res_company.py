# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    contract_license_product_id = fields.Many2one(
        "product.product",
        string="Licensing Product",
        # Companies created after the install start filled too (the
        # post_init_hook fills the ones that already existed).
        default=lambda self: (self.env.ref(
            "liber_copyright_contracts_licensing.product_rights_licensing",
            raise_if_not_found=False) or self.env["product.template"]
        ).product_variant_id,
        help="Product placed on the lines of rights-licensing invoices. Leave "
        "empty to use the \"Rights licensing\" service shipped with the module.",
    )
    contract_license_account_id = fields.Many2one(
        "account.account",
        string="Licensing Income Account",
        domain="[('company_ids', 'in', id)]",
        help="Income account of the licensing invoice lines. Leave empty to "
        "use the product's own income account.",
    )
    contract_license_journal_id = fields.Many2one(
        "account.journal",
        string="Licensing Journal",
        domain="[('type', '=', 'sale'), ('company_id', '=', id)]",
        help="Sales journal of the licensing invoices. Leave empty to use the "
        "company's first sales journal.",
    )

    def _contract_license_product(self):
        """Product of the licensing invoice lines (setting, else the module's)."""
        self.ensure_one()
        if self.contract_license_product_id:
            return self.contract_license_product_id
        template = self.env.ref(
            "liber_copyright_contracts_licensing.product_rights_licensing",
            raise_if_not_found=False)
        return template.product_variant_id if template else self.env["product.product"]

    def _contract_license_journal(self):
        """Sales journal of the licensing invoices (setting, else the first)."""
        self.ensure_one()
        if self.contract_license_journal_id:
            return self.contract_license_journal_id
        return self.env["account.journal"].sudo().search(
            [("type", "=", "sale"), ("company_id", "=", self.id)], limit=1)
