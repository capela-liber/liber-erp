# -*- coding: utf-8 -*-
from odoo import models

from ..services.gdrive_api import GDriveClient


class LiberCloudProvider(models.AbstractModel):
    _inherit = 'liber.cloud.provider'

    def _client_gdrive(self, account):
        return GDriveClient(account)

    def _manager_group_gdrive(self):
        return 'liber_gdrive.group_liber_gdrive_manager'
