# -*- coding: utf-8 -*-
"""The channel marking, on the screen, as the royalties manager does it.
See static/src/js/legacy_channel_tour.js."""
import os

from odoo.tests import HttpCase, tagged

from .common import ISBN, LegacyCase, write_csv

LOGIN = "legacy_channel_tour"


@tagged("post_install", "-at_install", "copyright_legacy_tour")
class TestLegacyChannelTour(HttpCase):
    def test_legacy_channel_tour(self):
        company = self.env.company
        self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Royalties Manager (channel tour)",
            "login": LOGIN,
            "password": LOGIN,
            "lang": "en_US",
            "company_id": company.id,
            "company_ids": [(6, 0, [company.id])],
            "group_ids": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("liber_copyright_contracts.group_contract_manager").id])],
        })
        team = self.env["crm.team"].create({"name": "Vendas especiais (tour)"})
        company.write({"contract_special_sales_team_ids": [(6, 0, team.ids)],
                       "contract_special_min_discount": 15.0})
        self.env["product.template"].create({
            "name": "Dom Casmurro", "type": "consu", "list_price": 10.0,
            "barcode": ISBN})
        path = write_csv(LegacyCase.SAMPLE)
        self.addCleanup(os.unlink, path)
        Sale = self.env["edlab.legacy.sale"]
        Sale._import_file(path)
        nf2 = Sale.search([("nf", "=", "2")])
        url = ("/odoo/action-liber_copyright_contracts_legacy.action_edlab_legacy_sale/"
               f"{nf2.id}")
        self.start_tour(url, "legacy_channel_tour", login=LOGIN)
        self.assertEqual(nf2.team_id, team)
        self.assertTrue(nf2.special_sale)
