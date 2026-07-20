# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    edlab_contract_ids = fields.Many2many(
        "edlab.contract",
        string="Copyright Contracts",
        compute="_compute_copyright_contracts",
        help="Contracts where this contact is a beneficiary.",
    )
    edlab_contract_count = fields.Integer(
        string="Contracts",
        compute="_compute_copyright_contracts",
    )

    def _compute_copyright_contracts(self):
        Contract = self.env["edlab.contract"]
        for partner in self:
            if isinstance(partner.id, int):
                contracts = Contract.search([("partner_ids", "in", partner.ids)])
            else:
                contracts = Contract.browse()
            partner.edlab_contract_ids = contracts
            partner.edlab_contract_count = len(contracts)

    def action_view_copyright_contracts(self):
        self.ensure_one()
        # No search_default_*: the domain already restricts the list to this
        # beneficiary's contracts, and the default would only add a search facet
        # showing the raw database id -- a filter that says nothing and cannot be
        # removed without widening the list. Whose contracts these are belongs in
        # the window title, where it can actually be read.
        return {
            "type": "ir.actions.act_window",
            "name": _("Contracts of %s", self.display_name),
            "res_model": "edlab.contract",
            "view_mode": "list,kanban,form",
            "domain": [("partner_ids", "in", self.ids)],
        }
