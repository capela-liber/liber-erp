# -*- coding: utf-8 -*-
import base64

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EdlabLegacyImportWizard(models.TransientModel):
    _name = "edlab.legacy.import"
    _description = "Import the legacy sales base"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    mode = fields.Selection([
        ("upload", "Upload the file"),
        ("path", "File already on the server"),
    ], required=True, default="upload")
    file = fields.Binary(string="CSV or XLSX")
    filename = fields.Char()
    path = fields.Char(
        string="Server path",
        help="Absolute path of the .csv or .xlsx on the Odoo server, for "
        "files too large to upload through the browser.")
    replace = fields.Boolean(
        string="Replace the current base", default=True,
        help="Delete this company's legacy rows before loading. Off, the "
        "file is appended (use it only for a complementary export).")
    current_count = fields.Integer(compute="_compute_current_count")

    @api.depends("company_id")
    def _compute_current_count(self):
        Sale = self.env["edlab.legacy.sale"]
        for wizard in self:
            wizard.current_count = Sale.search_count(
                [("company_id", "=", wizard.company_id.id)])

    def action_import(self):
        self.ensure_one()
        Sale = self.env["edlab.legacy.sale"]
        if self.mode == "upload":
            if not self.file:
                raise UserError(_("Choose the file first."))
            total = Sale._import_binary(
                base64.b64decode(self.file), self.filename or "base.csv",
                company=self.company_id, replace=self.replace)
        else:
            if not self.path:
                raise UserError(_("Type the path of the file on the server."))
            total = Sale._import_file(
                self.path, company=self.company_id, replace=self.replace)
        action = self.env["ir.actions.actions"]._for_xml_id(
            "liber_copyright_contracts_legacy.action_edlab_legacy_sale")
        action["context"] = {"search_default_group_source": 1}
        action["help"] = _("%s row(s) imported.", total)
        return action
