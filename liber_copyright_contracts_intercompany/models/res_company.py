# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # ------------------------------------------------------------------
    # Contract-holding side (the company whose contracts accrue)
    # ------------------------------------------------------------------
    contract_interco_source_company_ids = fields.Many2many(
        "res.company",
        "edlab_contract_interco_source_rel",
        "company_id",
        "source_company_id",
        string="Royalty Source Companies",
        help="Sister companies whose PAID sales also feed this company's "
        "royalty accrual. Empty = only this company's own sales accrue. "
        "Royalties accrued on these companies' sales are charged back to "
        "them through the intercompany royalty invoice.",
    )
    contract_interco_product_id = fields.Many2one(
        "product.product",
        string="Intercompany Royalties Product",
        help="Product placed on the intercompany royalty invoice lines. "
        "Leave empty to use the \"Royalties entre Empresas\" "
        "service product shipped with this module.",
    )
    contract_interco_journal_id = fields.Many2one(
        "account.journal",
        string="Intercompany Sale Journal",
        domain="[('type', '=', 'sale'), ('company_id', '=', id)]",
        help="Sale journal of the intercompany royalty invoice. Leave empty "
        "to use the company default sale journal.",
    )
    contract_interco_income_account_id = fields.Many2one(
        "account.account",
        string="Intercompany Income Account",
        domain="[('company_ids', 'in', id)]",
        help="Income account of the intercompany royalty invoice lines. "
        "Leave empty to use the product's default income account.",
    )
    contract_interco_markup = fields.Float(
        string="Intercompany Markup (%)",
        default=0.0,
        help="Administration percentage added on top of the accrued royalty "
        "when charging the selling company. 0 = charge the exact royalty.",
    )

    # ------------------------------------------------------------------
    # Selling side (the company whose sales are charged back)
    # ------------------------------------------------------------------
    contract_interco_purchase_journal_id = fields.Many2one(
        "account.journal",
        string="Intercompany Purchase Journal",
        domain="[('type', '=', 'purchase'), ('company_id', '=', id)]",
        help="Purchase journal of the mirrored intercompany vendor bill. "
        "Leave empty to use the company default purchase journal.",
    )
    contract_interco_expense_account_id = fields.Many2one(
        "account.account",
        string="Intercompany Expense Account",
        domain="[('company_ids', 'in', id)]",
        help="Expense account of the mirrored intercompany vendor bill "
        "lines. Leave empty to use the product's default expense account.",
    )

    def _contract_interco_product(self):
        """The product carried by the intercompany royalty invoice lines.

        Falls back to the module's own service product when the company has
        not chosen one -- the setting is a preference, not a prerequisite.
        """
        self.ensure_one()
        if self.contract_interco_product_id:
            return self.contract_interco_product_id
        template = self.env.ref(
            "liber_copyright_contracts_intercompany.product_interco_royalty",
            raise_if_not_found=False)
        return template.product_variant_id if template else self.env["product.product"]
