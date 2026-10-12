# -*- coding: utf-8 -*-
"""Every smart button of a contract with legacy sales, clicked on the real
screen by a contracts manager. Reported broken on 09/10/2026 after the
legacy layer added its own button to the family's box: the ORM returned the
right actions, so only a browser click can tell."""
import os
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from .common import ISBN, LegacyCase, write_csv

LOGIN = "contract_buttons_tour"


@tagged("post_install", "-at_install", "copyright_legacy_tour")
class TestContractButtonsTour(HttpCase):
    def test_every_contract_button_lands(self):
        company = self.env.company
        self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Contracts Manager (tour)",
            "login": LOGIN,
            "password": LOGIN,
            "lang": "en_US",
            "company_id": company.id,
            "company_ids": [(6, 0, [company.id])],
            "group_ids": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("account.group_account_invoice").id,
                self.env.ref("liber_copyright_contracts.group_contract_manager").id])],
        })
        author = self.env["res.partner"].create({"name": "Autor do Tour"})
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
        contract.royalty_line_ids._edlab_book_legacy()
        # A bill to pay, like the one on the reported contract.
        contract.action_generate_royalty_bills()
        self.assertTrue(contract.edlab_bill_to_pay_count)
        url = ("/odoo/action-liber_copyright_contracts.action_edlab_contract/"
               f"{contract.id}")
        self.start_tour(url, "contract_all_buttons_tour", login=LOGIN)
