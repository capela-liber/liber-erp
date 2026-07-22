# -*- coding: utf-8 -*-
import base64

from odoo import fields, models

from ..services.dropbox_api import DropboxClient


class LiberDropboxUpload(models.TransientModel):
    """Send one file into a mapped folder, through the folder's write gate."""
    _name = 'liber.dropbox.upload'
    _description = 'Upload to Dropbox'

    folder_id = fields.Many2one('liber.dropbox.folder', required=True)
    file_name = fields.Char(required=True)
    data = fields.Binary(required=True)

    def action_upload(self):
        self.ensure_one()
        self.folder_id._ensure_dropbox_access('write')
        client = DropboxClient(self.env)
        client.upload(f'{self.folder_id.path}/{self.file_name}',
                      base64.b64decode(self.data))
        # Mirror the new file right away so it appears without a manual sync.
        self.folder_id.action_sync()
        return self.folder_id.action_open_files()
