# -*- coding: utf-8 -*-
import base64
import os

from odoo import api, fields, models


class LiberCloudUpload(models.TransientModel):
    """Send one file into a mapped folder, through the folder's write gate."""
    _name = 'liber.cloud.upload'
    _description = 'Upload to Cloud Storage'

    folder_id = fields.Many2one(
        'liber.cloud.folder', required=True,
        domain="provider and [('provider', '=', provider)] or []")
    provider = fields.Selection(selection=[])
    file_name = fields.Char(required=True)
    data = fields.Binary(required=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if self.env.context.get('default_provider'):
            values['provider'] = self.env.context['default_provider']
        return values

    def action_upload(self):
        self.ensure_one()
        self.folder_id._ensure_access('write')
        # A name with separators would write outside the mapped folder;
        # only the base name ever travels.
        filename = os.path.basename(self.file_name.replace('\\', '/'))
        client = self.folder_id._client()
        client.upload(self.folder_id, filename, base64.b64decode(self.data))
        # Mirror the new file right away so it appears without waiting.
        self.folder_id.action_sync()
        return self.folder_id.action_open_files()
