# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    edlab_contract_ids = fields.Many2many(
        "edlab.contract",
        string="Copyright Contracts",
        compute="_compute_copyright_contracts",
        help="Contracts where this product is a licensed work.",
    )
    edlab_contract_count = fields.Integer(
        string="Contracts",
        compute="_compute_copyright_contracts",
    )

    def _compute_copyright_contracts(self):
        Contract = self.env["edlab.contract"]
        for product in self:
            if isinstance(product.id, int):
                contracts = Contract.search([("product_ids", "in", product.ids)])
            else:
                contracts = Contract.browse()
            product.edlab_contract_ids = contracts
            product.edlab_contract_count = len(contracts)

    def action_view_copyright_contracts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            # Same as on the beneficiary: the search default only produced a
            # facet with the raw id, on top of a domain that already filters.
            "name": _("Contracts of %s", self.display_name),
            "res_model": "edlab.contract",
            "view_mode": "list,kanban,form",
            "domain": [("product_ids", "in", self.ids)],
        }


class ProductProduct(models.Model):
    _inherit = "product.product"

    # The variant form is BUILT from the template form, so the stat button
    # lands here too. Template FIELDS reach the variant by _inherits
    # delegation; methods do not -- without this, every view that composes
    # the variant form (e.g. purchase's) fails to validate.
    def action_view_copyright_contracts(self):
        return self.product_tmpl_id.action_view_copyright_contracts()
