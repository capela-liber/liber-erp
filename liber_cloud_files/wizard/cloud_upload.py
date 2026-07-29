# -*- coding: utf-8 -*-
import base64
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LiberCloudUpload(models.TransientModel):
    """Send files into a mapped folder, through the folder's write gate."""
    _name = 'liber.cloud.upload'
    _description = 'Upload to Cloud Storage'

    folder_id = fields.Many2one(
        'liber.cloud.folder', required=True,
        domain="provider and [('provider', '=', provider)] or []")
    provider = fields.Selection(selection=[])
    attachment_ids = fields.Many2many(
        'ir.attachment', string='Files',
        help="One file or many: each travels to the folder on its own, and "
             "Odoo keeps no copy once they are sent.")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if self.env.context.get('default_provider'):
            values['provider'] = self.env.context['default_provider']
        return values

    def action_upload(self):
        self.ensure_one()
        if not self.attachment_ids:
            raise UserError(_("Pick at least one file to send."))
        self.folder_id._ensure_access('write')
        client = self.folder_id._client()
        for attachment in self.attachment_ids:
            # A name with separators would write outside the mapped folder;
            # only the base name ever travels.
            filename = os.path.basename(
                (attachment.name or '').replace('\\', '/'))
            client.upload(self.folder_id, filename,
                          base64.b64decode(attachment.datas))
        # The bytes live in the storage now; Odoo keeps no second copy.
        self.attachment_ids.sudo().unlink()
        # Mirror the new files right away so they appear without waiting.
        self.folder_id.action_sync()
        return self.folder_id.action_open_files()
