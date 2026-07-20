# -*- coding: utf-8 -*-
"""Tests for the royalty engine: tier selection on CUMULATIVE quantity,
the accrual amounts, idempotency, the gross-vs-net base and the advance.

All money math is hand-computed in the asserts: 7% of a R$ 800,00 sale is
R$ 56,00 — if a refactor silently changes the base or the tier lookup, these
numbers move and the test screams."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "copyright_analytics")
class TestRoyaltyAnalytics(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.author = cls.env["res.partner"].create({"name": "Machado de Assis"})
        cls.customer = cls.env["res.partner"].create({"name": "Livraria Cliente"})
        cls.book = cls.env["product.template"].create({
            "name": "Dom Casmurro", "type": "consu", "list_price": 10.0})
        cls.contract = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [(0, 0, {
                "partner_id": cls.author.id,
                "product_id": cls.book.id,
                "tier_ids": [
                    (0, 0, {"qty_from": 0, "qty_to": 100, "percentage": 7.0}),
                    (0, 0, {"qty_from": 101, "qty_to": 0, "percentage": 8.0}),
                ],
            })],
        })
        cls.royalty = cls.contract.royalty_line_ids
        cls.royalty.action_create_analytic_account()
        cls.account = cls.royalty.analytic_account_id

    def _invoice(self, qty, price=10.0, discount=0.0, days_ago=0):
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_date": fields.Date.today() - timedelta(days=days_ago),
            "invoice_line_ids": [(0, 0, {
                "product_id": self.book.product_variant_id.id,
                "quantity": qty,
                "price_unit": price,
                "discount": discount,
            })],
        })
        move.action_post()
        return move

    def _accruals(self):
        return self.env["account.analytic.line"].search([
            ("account_id", "=", self.account.id),
            ("edlab_source_move_line_id", "!=", False),
        ])

    def test_percentage_follows_cumulative_qty(self):
        self.assertEqual(self.royalty._royalty_percentage_for_qty(50), 7.0)
        self.assertEqual(self.royalty._royalty_percentage_for_qty(100), 7.0)
        self.assertEqual(self.royalty._royalty_percentage_for_qty(101), 8.0)
        self.assertEqual(self.royalty._royalty_percentage_for_qty(5000), 8.0)

    def test_booking_crosses_tiers_across_invoices(self):
        """80 copies at 7%, then 40 more pushing the cumulative into 8%."""
        inv1 = self._invoice(80, days_ago=2)
        inv2 = self._invoice(40, days_ago=1)
        self.royalty._book_royalties_from_invoices(inv1 + inv2)

        lines = self._accruals().sorted("date")
        self.assertEqual(len(lines), 2)
        # 80 x 10,00 = 800,00 @ 7% -> -56,00
        self.assertAlmostEqual(lines[0].amount, -56.0, places=2)
        # cumulative 120 -> 8%: 40 x 10,00 = 400,00 @ 8% -> -32,00
        self.assertAlmostEqual(lines[1].amount, -32.0, places=2)
        self.assertEqual(lines[1].edlab_royalty_percentage, 8.0)

    def test_booking_is_idempotent(self):
        inv = self._invoice(10)
        self.royalty._book_royalties_from_invoices(inv)
        self.royalty._book_royalties_from_invoices(inv)
        self.assertEqual(len(self._accruals()), 1,
                         "re-running must never book the same line twice")

    def test_on_sales_price_uses_gross_base(self):
        """With 50% discount: net base pays on 50, gross base pays on 100."""
        self.royalty.on_sales_price = True
        inv = self._invoice(10, price=10.0, discount=50.0)
        self.royalty._book_royalties_from_invoices(inv)
        line = self._accruals()
        # gross: 10 x 10,00 = 100,00 @ 7% -> -7,00 (net would be -3,50)
        self.assertAlmostEqual(line.amount, -7.0, places=2)

    def test_advance_booked_once_at_signature(self):
        self.royalty.recoupable_advance = 100.0
        self.royalty._book_royalties_from_invoices(
            self.env["account.move"])
        self.royalty._book_royalties_from_invoices(
            self.env["account.move"])
        advances = self.env["account.analytic.line"].search([
            ("account_id", "=", self.account.id),
            ("edlab_advance_line_id", "!=", False),
        ])
        self.assertEqual(len(advances), 1)
        self.assertAlmostEqual(advances.amount, 100.0, places=2)
        self.assertEqual(advances.date, self.contract.signature_date)

    def test_out_of_term_sale_accrues_nothing(self):
        """A sale invoiced before the signature never earns royalties."""
        inv = self._invoice(10, days_ago=60)  # before signature (30 days ago)
        self.royalty._book_royalties_from_invoices(inv)
        self.assertFalse(self._accruals())
