# -*- coding: utf-8 -*-
"""Tests for the contract smart buttons: the analytic-accounts button and the
beneficiaries button. The rule under test: a single target opens straight on
its form (the button is a LINK, not a search), several open as a list, and the
counters agree with what the click will show."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "copyright_analytics")
class TestContractSmartButtons(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.author = cls.env["res.partner"].create({"name": "Machado de Assis"})
        cls.author2 = cls.env["res.partner"].create({"name": "Lima Barreto"})
        cls.book = cls.env["product.template"].create({
            "name": "Dom Casmurro", "type": "consu", "list_price": 10.0})
        cls.book2 = cls.env["product.template"].create({
            "name": "O Cortiço", "type": "consu", "list_price": 12.0})
        cls.contract = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [(0, 0, {
                "partner_id": cls.author.id,
                "product_id": cls.book.id,
            })],
        })

    def _add_line(self, partner, product):
        self.contract.write({"royalty_line_ids": [(0, 0, {
            "partner_id": partner.id,
            "product_id": product.id,
        })]})

    # --- Contas Analíticas -------------------------------------------------

    def test_single_analytic_opens_its_form(self):
        """One account: the click must land ON the analytic, not on a list."""
        line = self.contract.royalty_line_ids
        line.action_create_analytic_account()
        account = line.analytic_account_id

        self.assertEqual(self.contract.edlab_analytic_count, 1)
        action = self.contract.action_view_contract_analytics()
        self.assertEqual(action["res_model"], "account.analytic.account")
        self.assertEqual(action["res_id"], account.id)
        self.assertEqual(action["view_mode"], "form")
        self.assertNotIn("domain", action)

    def test_many_analytics_open_a_list(self):
        self._add_line(self.author2, self.book2)
        lines = self.contract.royalty_line_ids
        lines.action_create_analytic_account()
        accounts = lines.analytic_account_id

        self.assertEqual(self.contract.edlab_analytic_count, 2)
        action = self.contract.action_view_contract_analytics()
        self.assertEqual(action["view_mode"], "list,form")
        self.assertEqual(action["domain"], [("id", "in", accounts.ids)])
        self.assertNotIn("res_id", action)

    def test_no_analytic_opens_empty_list(self):
        """Zero accounts is the state that needs surfacing (nothing can be
        booked yet): the button stays clickable and opens an empty list."""
        self.assertEqual(self.contract.edlab_analytic_count, 0)
        action = self.contract.action_view_contract_analytics()
        self.assertEqual(action["view_mode"], "list,form")
        self.assertEqual(action["domain"], [("id", "in", [])])

    # --- Favorecidos -------------------------------------------------------

    def test_single_beneficiary_opens_their_card(self):
        self.assertEqual(self.contract.beneficiary_count, 1)
        action = self.contract.action_view_contract_beneficiaries()
        self.assertEqual(action["res_model"], "res.partner")
        self.assertEqual(action["res_id"], self.author.id)
        self.assertEqual(action["view_mode"], "form")

    def test_repeated_beneficiary_counts_once(self):
        """Two works of the SAME author: one person, one card, count of one."""
        self._add_line(self.author, self.book2)
        self.assertEqual(self.contract.beneficiary_count, 1)
        action = self.contract.action_view_contract_beneficiaries()
        self.assertEqual(action["res_id"], self.author.id)

    def test_many_beneficiaries_open_a_list(self):
        self._add_line(self.author2, self.book2)
        self.assertEqual(self.contract.beneficiary_count, 2)
        action = self.contract.action_view_contract_beneficiaries()
        self.assertEqual(action["view_mode"], "list,form")
        self.assertEqual(
            action["domain"],
            [("id", "in", self.contract.royalty_line_ids.partner_id.ids)])

    # --- erro --------------------------------------------------------------

    def test_buttons_require_a_single_contract(self):
        other = self.contract.copy()
        both = self.contract + other
        with self.assertRaises(ValueError):
            both.action_view_contract_analytics()
        with self.assertRaises(ValueError):
            both.action_view_contract_beneficiaries()
