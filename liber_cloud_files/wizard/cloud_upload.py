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
        domain="[('id', 'in', allowed_folder_ids)]")
    allowed_folder_ids = fields.Many2many(
        'liber.cloud.folder', compute='_compute_allowed_folder_ids',
        string='Folders You May Fill')
    provider = fields.Selection(selection=[])
    attachment_ids = fields.Many2many(
        'ir.attachment', string='Files',
        help="One file or many: each travels to the folder on its own, and "
             "Odoo keeps no copy once they are sent.")

    @api.depends('provider')
    @api.depends_context('uid')
    def _compute_allowed_folder_ids(self):
        """Offer only the folders this person may actually fill.

        Until now the list narrowed by provider alone, so it showed every
        folder the reader could SEE -- and reading is not writing. Someone
        with read-only access to a repository was offered it, picked it,
        attached the files and only then met "You do not have write
        access". The gate held, but the screen had promised otherwise,
        and a promise the gate breaks is a bug even when nothing leaks.

        Same rule as _ensure_access('write'), on purpose: managers and
        administrators do not bypass it either. Configuring the shelf is
        one power, filling it is another.
        """
        Folder = self.env['liber.cloud.folder']
        groups = self.env.user.sudo().all_group_ids
        for wizard in self:
            domain = ([('provider', '=', wizard.provider)]
                      if wizard.provider else [])
            folders = Folder.search(domain)
            wizard.allowed_folder_ids = folders if self.env.su else \
                folders.filtered(lambda f: f.sudo().write_group_ids & groups)

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
