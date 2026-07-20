# -*- coding: utf-8 -*-
"""Tests for the royalty statement: its total must equal the open balance
(the invariant the whole statement is built on), and the advance can reduce
what is payable but never below zero."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "copyright_reports")
class TestRoyaltyStatement(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.author = cls.env["res.partner"].create({"name": "Lima Barreto"})
        cls.customer = cls.env["res.partner"].create({"name": "Livraria Cliente"})
        cls.book = cls.env["product.template"].create({
            "name": "Policarpo Quaresma", "type": "consu", "list_price": 10.0})
        cls.contract = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [(0, 0, {
                "partner_id": cls.author.id,
                "product_id": cls.book.id,
                "tier_ids": [(0, 0, {"qty_from": 0, "qty_to": 0,
                                     "percentage": 10.0})],
            })],
        })
        cls.royalty = cls.contract.royalty_line_ids
        cls.royalty.action_create_analytic_account()

    def _sell_and_book(self, qty, price=10.0):
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [(0, 0, {
                "product_id": self.book.product_variant_id.id,
                "quantity": qty,
                "price_unit": price,
            })],
        })
        move.action_post()
        self.royalty._book_royalties_from_invoices(move)

    def test_statement_total_equals_open_balance(self):
        """The docstring's promise: statement total == _edlab_open_balance."""
        self._sell_and_book(10)     # 100,00 @ 10% -> 10,00 owed
        statement = self.author._edlab_royalty_statement()
        self.assertAlmostEqual(statement["accrued"], 10.0, places=2)
        self.assertAlmostEqual(
            statement["total"], self.royalty._edlab_open_balance(), places=2)
        self.assertEqual(len(statement["rows"]), 1)

    def test_advance_reduces_total_but_never_below_zero(self):
        """Advance bigger than the accruals: recoup caps at the accrued."""
        self.royalty.recoupable_advance = 1000.0
        self._sell_and_book(10)     # accrues 10,00; advance dwarfs it
        statement = self.author._edlab_royalty_statement()
        self.assertAlmostEqual(
            statement["advance_recouped"], statement["accrued"], places=2)
        self.assertAlmostEqual(statement["total"], 0.0, places=2,
                               msg="an author never owes US on a statement")

    def test_manual_irrf_percentage(self):
        if "edlab_irrf_mode" in self.author._fields:
            self.author.edlab_irrf_mode = "manual"
        self.author.edlab_irrf_percentage = 15.0
        self._sell_and_book(100)    # 1.000,00 @ 10% -> 100,00 owed
        statement = self.author._edlab_royalty_statement()
        self.assertAlmostEqual(statement["irrf"], 15.0, places=2)
        self.assertAlmostEqual(
            statement["net"], statement["total"] - statement["irrf"], places=2)
