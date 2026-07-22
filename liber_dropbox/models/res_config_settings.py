# -*- coding: utf-8 -*-
from odoo import fields, models, _

from ..services.dropbox_api import DropboxClient


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    liber_dropbox_app_key = fields.Char(
        string='App Key',
        config_parameter='liber_dropbox.app_key')
    liber_dropbox_app_secret = fields.Char(
        string='App Secret',
        config_parameter='liber_dropbox.app_secret')
    liber_dropbox_refresh_token = fields.Char(
        string='Refresh Token',
        config_parameter='liber_dropbox.refresh_token',
        help="Long-lived token from the one-time authorization flow; see "
             "the module's NOTES.md for the two curl calls that mint it.")
    liber_dropbox_share_ttl_days = fields.Integer(
        string='Shared Links Expire After (days)',
        config_parameter='liber_dropbox.share_ttl_days',
        default=30,
        help="Every shared link created from Odoo dies after this many "
             "days; sharing again renews the deadline. 0 creates links "
             "that never expire. Expiration requires a paid Dropbox plan.")

    def action_liber_dropbox_test(self):
        account = DropboxClient(self.env).check()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Dropbox connected"),
                'message': _(
                    "Authenticated as %(name)s (%(email)s).",
                    name=account.get('name', {}).get('display_name', '?'),
                    email=account.get('email', '?')),
                'sticky': False,
            },
        }
