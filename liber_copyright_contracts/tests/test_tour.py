# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCopyrightContractsTour(HttpCase):
    def test_copyright_contracts_tour(self):
        """Drive the whole contract life end to end through the real UI:
        create -> the renewal term auto-fills from the dates -> add a royalty
        line (beneficiary x work) with two copies tiers and a recoupable
        advance -> save -> validate -> renew -> reassign the responsible via the
        Action menu -> cancel."""
        self.start_tour(
            "/odoo", "copyright_contracts_tour", login="admin"
        )
