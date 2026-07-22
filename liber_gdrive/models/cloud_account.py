# -*- coding: utf-8 -*-
from odoo import fields, models


class LiberCloudAccount(models.Model):
    _inherit = 'liber.cloud.account'

    provider = fields.Selection(
        selection_add=[('gdrive', 'Google Drive')],
        ondelete={'gdrive': 'cascade'})
    gdrive_client_id = fields.Char(string='Client ID')
    gdrive_client_secret = fields.Char(string='Client Secret')
    gdrive_refresh_token = fields.Char(
        string='Refresh Token',
        help="Long-lived token from the one-time OAuth authorization of "
             "the company's Google account; see the module's NOTES.md.")
