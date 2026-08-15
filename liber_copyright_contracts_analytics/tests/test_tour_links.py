# -*- coding: utf-8 -*-
"""Browser proof of the smart-button links. The reported bug was a click that
returned a perfectly valid action over RPC while the screen never changed --
only a real browser click through the tour runner can catch that class of
failure, so the unit tests on the action dicts are not enough here."""
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestContractLinkTours(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        author = cls.env["res.partner"].create({"name": "Machado de Assis"})
        book = cls.env["product.template"].create({
            "name": "Dom Casmurro", "type": "consu", "list_price": 10.0})
        cls.contract = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [(0, 0, {
                "partner_id": author.id,
                "product_id": book.id,
            })],
        })
        cls.contract.royalty_line_ids.action_create_analytic_account()

    def _contract_url(self):
        return (
            "/odoo/action-liber_copyright_contracts.action_edlab_contract/"
            f"{self.contract.id}"
        )

    def test_analytics_button_lands_on_the_account(self):
        self.start_tour(
            self._contract_url(), "contract_analytics_link_tour", login="admin")

    def test_beneficiaries_button_lands_on_the_card(self):
        self.start_tour(
            self._contract_url(), "contract_beneficiaries_link_tour",
            login="admin")
