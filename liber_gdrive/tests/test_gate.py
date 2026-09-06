# -*- coding: utf-8 -*-
"""The shared gate suite, run against this provider's shelf."""
from odoo.tests import tagged

from odoo.addons.liber_cloud_files.tests.common import CloudGateCase


# The decorator is repeated here on purpose: @tagged stamps the module a
# class belongs to, and an inherited stamp would file these tests under
# the chassis -- where nothing runs them.
@tagged('post_install', '-at_install')
class TestgdriveGate(CloudGateCase):
    PROVIDER = 'gdrive'
    ACCOUNT_VALS = {'gdrive_client_id': 'i', 'gdrive_client_secret': 's', 'gdrive_refresh_token': 'r'}
    MODULE = 'liber_gdrive'
