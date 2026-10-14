# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    contract_authors_alias = fields.Char(
        related="company_id.contract_authors_alias", readonly=False)
    contract_authors_alias_domain = fields.Char(
        compute="_compute_contract_authors_alias_domain")

    @api.depends("company_id")
    def _compute_contract_authors_alias_domain(self):
        for settings in self:
            domain = settings.company_id.alias_domain_id.name
            settings.contract_authors_alias_domain = "@%s" % domain if domain else ""

    def set_values(self):
        super().set_values()
        # Saving the mailbox creates (or renames) the record behind it.
        self.company_id._edlab_authors_team()
        self.company_id._edlab_sync_authors_team()
