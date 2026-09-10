# -*- coding: utf-8 -*-
"""The screen, as the accountant sees it: the Mirror button on the source and
the Source button plus field on the mirror. Two tours, one per company, because
the web client shows one company at a time; each opens the record's own form."""
from odoo.tests import HttpCase, tagged

from .common import MirrorFixture


@tagged("post_install", "-at_install", "intercompany_mirror_tour")
class TestMirrorLinkTour(MirrorFixture, HttpCase):

    def _user(self, login, company):
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Contador do Tour (%s)" % company.name,
            "login": login,
            "password": login,
            "lang": "en_US",
            "company_id": company.id,
            "company_ids": [(6, 0, [company.id])],
            "group_ids": [(4, self.env.ref("account.group_account_invoice").id)],
        })

    def test_mirror_link_tours(self):
        source, dest = self._two_companies()
        product = self._wire(source, dest)
        invoice, mirror = self._post_pair(source, dest, product)
        self.assertEqual(len(mirror), 1)
        self._user("contador_tour_src", source)
        self._user("contador_tour_dst", dest)

        self.start_tour("/odoo/action-account.action_move_out_invoice_type/%d" % invoice.id,
                        "mirror_link_source_tour", login="contador_tour_src")
        self.start_tour("/odoo/action-account.action_move_in_invoice_type/%d" % mirror.id,
                        "mirror_link_mirror_tour", login="contador_tour_dst")
