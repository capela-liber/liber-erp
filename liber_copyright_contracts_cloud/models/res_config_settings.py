# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    contract_cloud_provider = fields.Selection(
        related="company_id.contract_cloud_provider", readonly=False)
    contract_cloud_folder_ids = fields.Many2many(
        related="company_id.contract_cloud_folder_ids", readonly=False)

    @api.onchange("contract_cloud_provider")
    def _onchange_contract_cloud_provider(self):
        """Switching storage drops the folders of the previous one."""
        provider = self.contract_cloud_provider
        if provider:
            self.contract_cloud_folder_ids = self.contract_cloud_folder_ids.filtered(
                lambda f: f.provider == provider)
