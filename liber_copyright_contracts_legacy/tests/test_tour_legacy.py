# -*- coding: utf-8 -*-
"""The screen, as the royalties manager sees it: contract tab, smart
button, legacy list and a row's CFOP. See static/src/js/legacy_sales_tour.js."""
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

import os

from .common import ISBN, LegacyCase, write_csv

LOGIN = "legacy_manager_tour"


@tagged("post_install", "-at_install", "copyright_legacy_tour")
class TestLegacySalesTour(HttpCase):
    def test_legacy_sales_tour(self):
        company = self.env.company
        self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Royalties Manager (tour)",
            "login": LOGIN,
            "password": LOGIN,
            "lang": "en_US",
            "company_id": company.id,
            "company_ids": [(6, 0, [company.id])],
            # Internal user AND royalties manager: the manager group alone
            # does not make an internal user, and /odoo turns a non-internal
            # login away with a "Forbidden" page (the screenshot told).
            "group_ids": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("liber_copyright_contracts.group_contract_manager").id])],
        })
        author = self.env["res.partner"].create({"name": "Machado de Assis"})
        book = self.env["product.template"].create({
            "name": "Dom Casmurro", "type": "consu", "list_price": 10.0,
            "barcode": ISBN})
        today = fields.Date.today()
        contract = self.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "legacy_enabled": True,
            "royalty_line_ids": [(0, 0, {
                "partner_id": author.id, "product_id": book.id,
                "tier_ids": [(0, 0, {"qty_from": 0, "qty_to": 0, "percentage": 7.0})],
            })],
        })
        contract.royalty_line_ids.action_create_analytic_account()
        path = write_csv(LegacyCase.SAMPLE)
        self.addCleanup(os.unlink, path)
        self.env["edlab.legacy.sale"]._import_file(path)
        url = ("/odoo/action-liber_copyright_contracts.action_edlab_contract/"
               f"{contract.id}")
        self.start_tour(url, "legacy_sales_tour", login=LOGIN)
