# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model
    def _selection_contract_cloud_provider(self):
        """Whatever providers are installed (Dropbox, Google Drive, GitHub):
        the provider modules add themselves to the folder's selection."""
        return self.env["liber.cloud.folder"]._fields[
            "provider"]._description_selection(self.env)

    contract_cloud_provider = fields.Selection(
        selection="_selection_contract_cloud_provider",
        string="Contract documents storage",
        help="Where the house keeps its contracts: GitHub, Google Drive or "
        "Dropbox. Narrows the folders below to that storage.",
    )
    contract_cloud_folder_ids = fields.Many2many(
        "liber.cloud.folder",
        "res_company_contract_cloud_folder_rel",
        "company_id", "folder_id",
        string="Contract document folders",
        help="Mapped Cloud Files folders that hold the contracts' "
        "documents. A contract's document picker only offers files from "
        "these folders.",
    )

    def _contract_cloud_folders(self):
        """The folders that count: the chosen ones, of the chosen storage.

        Not a constraint: Settings writes the storage and the folders one
        related field at a time, so a constraint would fire between the two
        writes when switching storage. Folders of another storage are simply
        ignored until someone clears them."""
        self.ensure_one()
        folders = self.sudo().contract_cloud_folder_ids
        if self.contract_cloud_provider:
            folders = folders.filtered(
                lambda f: f.provider == self.contract_cloud_provider)
        return folders
