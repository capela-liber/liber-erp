# -*- coding: utf-8 -*-
from odoo import models

from ..services.dropbox_api import DropboxClient


class LiberCloudProvider(models.AbstractModel):
    _inherit = 'liber.cloud.provider'

    def _client_dropbox(self, account):
        return DropboxClient(account)

    def _manager_group_dropbox(self):
        return 'liber_dropbox.group_liber_dropbox_manager'
