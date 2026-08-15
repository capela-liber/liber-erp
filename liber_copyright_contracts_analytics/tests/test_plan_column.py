# -*- coding: utf-8 -*-
"""The royalty lines must live in the account's PLAN column, not only in
``account_id``: core aggregates per plan (the account form's balance / "Gross
Margin", the plan reports), so a line missing the plan column is invisible
money -- the account showed R$ 0,00 over hundreds of entries. These tests pin
the double write on booking and the backfill that repairs pre-existing data."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "copyright_analytics")
class TestRoyaltyPlanColumn(TransactionCase):
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
                "tier_ids": [(0, 0, {"qty_from": 0, "qty_to": 0,
                                     "percentage": 10.0})],
            })],
        })
        cls.royalty = cls.contract.royalty_line_ids
        cls.royalty.action_create_analytic_account()
        cls.account = cls.royalty.analytic_account_id
        cls.plan_column = cls.account.plan_id._column_name()

    def _book_one_sale(self, qty=10):
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [(0, 0, {
                "product_id": self.book.product_variant_id.id,
                "quantity": qty,
                "price_unit": 10.0,
            })],
        })
        move.action_post()
        self.royalty._book_royalties_from_invoices(move)
        return move

    def _lines(self):
        return self.env["account.analytic.line"].search(
            [("account_id", "=", self.account.id)])

    def test_copyright_plan_is_not_the_project_plan(self):
        """Guard: if the copyright plan ever collapses into the Project plan,
        every other assertion here tests nothing."""
        self.assertNotEqual(self.plan_column, "account_id")

    def test_booking_fills_both_columns_and_core_balance(self):
        self._book_one_sale(qty=10)
        lines = self._lines()
        self.assertTrue(lines)
        for line in lines:
            self.assertEqual(line[self.plan_column], self.account,
                             "plan column missing: core aggregation is blind")
        # The number on the account form ("Gross Margin") comes from the core
        # per-plan compute: 10 x 10,00 @ 10% -> -10,00.
        self.assertAlmostEqual(self.account.balance, -10.0, places=2)

    def test_auto_account_search_finds_the_lines(self):
        """The core account-form button opens [('auto_account_id','=',id)]:
        every booked line must be reachable through it, and the plan-column
        OR account_id double write must not duplicate any row."""
        self._book_one_sale(qty=10)
        via_auto = self.env["account.analytic.line"].search(
            [("auto_account_id", "=", self.account.id)])
        self.assertEqual(via_auto, self._lines())

    def test_backfill_repairs_legacy_lines(self):
        """Lines booked before the double write have only account_id: the
        backfill must mirror them into the plan column (idempotently), and
        the core balance must come back to life."""
        self._book_one_sale(qty=10)
        lines = self._lines()
        lines.write({self.plan_column: False})
        self.env.invalidate_all()
        self.assertAlmostEqual(self.account.balance, 0.0, places=2,
                               msg="legacy shape: core sees nothing")

        moved = self.env["account.analytic.line"]._edlab_backfill_plan_columns()
        self.assertEqual(moved, len(lines))
        self.env.invalidate_all()
        self.assertAlmostEqual(self.account.balance, -10.0, places=2)
        # idempotent: a second run has nothing left to move
        self.assertEqual(
            self.env["account.analytic.line"]._edlab_backfill_plan_columns(), 0)

    def test_backfill_carries_manual_lines_on_copyright_accounts(self):
        """A hand-typed entry on a copyright account has none of the royalty
        markers, but it is just as invisible to the plan aggregation."""
        manual = self.env["account.analytic.line"].sudo().create({
            "name": "ajuste manual",
            "account_id": self.account.id,
            "date": fields.Date.today(),
            "amount": -5.0,
            "company_id": self.account.company_id.id,
        })
        manual.write({self.plan_column: False})
        self.env["account.analytic.line"]._edlab_backfill_plan_columns()
        self.assertEqual(manual[self.plan_column], self.account)
