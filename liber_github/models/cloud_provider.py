# -*- coding: utf-8 -*-
from odoo import models

from ..services.github_api import GitHubClient


class LiberCloudProvider(models.AbstractModel):
    _inherit = 'liber.cloud.provider'

    def _client_github(self, account):
        return GitHubClient(account)

    def _manager_group_github(self):
        return 'liber_github.group_liber_github_manager'
