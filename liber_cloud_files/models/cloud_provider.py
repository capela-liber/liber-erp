# -*- coding: utf-8 -*-
from odoo import models


class LiberCloudProvider(models.AbstractModel):
    """The registry where provider modules plug in.

    A provider module inherits this model and adds two methods named
    after its selection key:

        def _client_dropbox(self, account): return DropboxClient(account)
        def _manager_group_dropbox(self): return 'liber_dropbox.group_...'

    The base dispatches by name; nothing here knows any provider.
    """
    _name = 'liber.cloud.provider'
    _description = 'Cloud Storage Provider Registry'

    def _client(self, account):
        return getattr(self, '_client_%s' % account.provider)(account)

    def _manager_group(self, provider):
        return getattr(self, '_manager_group_%s' % provider)()
