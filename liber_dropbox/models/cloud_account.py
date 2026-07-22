# -*- coding: utf-8 -*-
from odoo import fields, models


class LiberCloudAccount(models.Model):
    _inherit = 'liber.cloud.account'

    provider = fields.Selection(
        selection_add=[('dropbox', 'Dropbox')],
        ondelete={'dropbox': 'cascade'})
    dropbox_app_key = fields.Char(string='App Key')
    dropbox_app_secret = fields.Char(string='App Secret')
    dropbox_refresh_token = fields.Char(
        string='Refresh Token',
        help="Long-lived token from the one-time authorization flow; see "
             "the module's NOTES.md for the two curl calls that mint it.")
