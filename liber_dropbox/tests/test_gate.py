# -*- coding: utf-8 -*-
"""The shared gate suite, run against this provider's shelf."""
from odoo.tests import tagged

from odoo.addons.liber_cloud_files.tests.common import CloudGateCase


# The decorator is repeated here on purpose: @tagged stamps the module a
# class belongs to, and an inherited stamp would file these tests under
# the chassis -- where nothing runs them.
@tagged('post_install', '-at_install')
class TestdropboxGate(CloudGateCase):
    PROVIDER = 'dropbox'
    ACCOUNT_VALS = {'dropbox_app_key': 'k', 'dropbox_app_secret': 's', 'dropbox_refresh_token': 'r'}
    MODULE = 'liber_dropbox'
