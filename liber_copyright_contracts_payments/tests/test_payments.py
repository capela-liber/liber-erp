# -*- coding: utf-8 -*-
"""Tests for royalty payments: the open balance the bill is built from,
the one-bill-per-beneficiary grouping and the no-duplicate-bill guard."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "copyright_payments")
class TestRoyaltyPayments(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.author = cls.env["res.partner"].create({"name": "Clarice Lispector"})
        cls.customer = cls.env["res.partner"].create({"name": "Livraria Cliente"})
        cls.book_a = cls.env["product.template"].create({
            "name": "A Hora da Estrela", "type": "consu", "list_price": 10.0})
        cls.book_b = cls.env["product.template"].create({
            "name": "Água Viva", "type": "consu", "list_price": 20.0})
        cls.contract = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [
                (0, 0, {
                    "partner_id": cls.author.id,
                    "product_id": cls.book_a.id,
                    "tier_ids": [(0, 0, {"qty_from": 0, "qty_to": 0,
                                         "percentage": 10.0})],
                }),
                (0, 0, {
                    "partner_id": cls.author.id,
                    "product_id": cls.book_b.id,
                    "tier_ids": [(0, 0, {"qty_from": 0, "qty_to": 0,
                                         "percentage": 10.0})],
                }),
            ],
        })
        cls.lines = cls.contract.royalty_line_ids
        cls.lines.action_create_analytic_account()

    def _sell_and_book(self, book, qty, price):
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [(0, 0, {
                "product_id": book.product_variant_id.id,
                "quantity": qty,
                "price_unit": price,
            })],
        })
        move.action_post()
        self.lines._book_royalties_from_invoices(move)

    def _bills(self):
        return self.env["account.move"].search([
            ("edlab_contract_id", "=", self.contract.id),
            ("move_type", "=", "in_invoice"),
        ])

    def test_open_balance_equals_accruals(self):
        self._sell_and_book(self.book_a, 10, 10.0)   # 100,00 @ 10% -> 10,00
        line_a = self.lines.filtered(lambda l: l.product_id == self.book_a)
        self.assertAlmostEqual(line_a._edlab_open_balance(), 10.0, places=2)
        line_b = self.lines.filtered(lambda l: l.product_id == self.book_b)
        self.assertAlmostEqual(line_b._edlab_open_balance(), 0.0, places=2)

    def test_one_bill_per_beneficiary_one_line_per_work(self):
        self._sell_and_book(self.book_a, 10, 10.0)   # -> 10,00
        self._sell_and_book(self.book_b, 5, 20.0)    # -> 10,00
        self.contract.action_generate_royalty_bills()

        bill = self._bills()
        self.assertEqual(len(bill), 1,
                         "same beneficiary, two works -> ONE bill")
        self.assertEqual(bill.partner_id, self.author)
        royalty_lines = bill.invoice_line_ids.filtered("edlab_royalty_line_id")
        self.assertEqual(len(royalty_lines), 2)
        for bline in royalty_lines:
            self.assertAlmostEqual(bline.price_unit, 10.0, places=2)

    def test_no_duplicate_bill_while_one_is_open(self):
        self._sell_and_book(self.book_a, 10, 10.0)
        self.contract.action_generate_royalty_bills()
        first = self._bills()
        self.contract.action_generate_royalty_bills()
        self.assertEqual(self._bills(), first,
                         "an open bill must block a second one")

    def test_bill_shows_the_advance_as_a_negative_line(self):
        """Advance 5,00, royalties 10,00: the bill must read GROSS 10,00
        minus a visible 'advance recouped' line of 5,00 — total 5,00 — not
        an opaque net 5,00 the author cannot reconcile."""
        line_a = self.lines.filtered(lambda l: l.product_id == self.book_a)
        line_a.recoupable_advance = 5.0
        self._sell_and_book(self.book_a, 10, 10.0)   # 100,00 @ 10% -> 10,00
        self.contract.action_generate_royalty_bills()

        bill = self._bills()
        self.assertAlmostEqual(bill.amount_total, 5.0, places=2)
        blines = bill.invoice_line_ids.filtered("edlab_royalty_line_id")
        self.assertEqual(len(blines), 2)
        amounts = sorted(blines.mapped("price_unit"))
        self.assertAlmostEqual(amounts[0], -5.0, places=2)
        self.assertAlmostEqual(amounts[1], 10.0, places=2)

    def test_generation_books_a_stray_advance_first(self):
        """An advance typed on the line but missing from the analytic (the
        ordering hole) must NOT inflate the bill to the gross: generation
        books it first, then computes."""
        line_a = self.lines.filtered(lambda l: l.product_id == self.book_a)
        # Bypass the ORM write hook on purpose: this is exactly the drifted
        # state (field set, entry absent) the generator must repair.
        self.env.cr.execute(
            "UPDATE edlab_contract_royalty_line SET recoupable_advance=5.0 "
            "WHERE id=%s", [line_a.id])
        line_a.invalidate_recordset()
        self._advance_entries = self.env["account.analytic.line"].sudo().search(
            [("edlab_advance_line_id", "=", line_a.id)])
        self.assertFalse(self._advance_entries, "drift precondition")

        self._sell_and_book(self.book_a, 10, 10.0)   # booking also repairs
        self.env["account.analytic.line"].sudo().search(
            [("edlab_advance_line_id", "=", line_a.id)]).unlink()  # re-drift
        self.contract.action_generate_royalty_bills()

        bill = self._bills()
        self.assertAlmostEqual(bill.amount_total, 5.0, places=2,
                               msg="the bill must pay NET of the advance")
        self.assertTrue(self.env["account.analytic.line"].sudo().search(
            [("edlab_advance_line_id", "=", line_a.id)]),
            "generation must (re)book the advance entry")

    def test_draft_bill_does_not_stamp_payment(self):
        self._sell_and_book(self.book_a, 10, 10.0)
        self.contract.action_generate_royalty_bills()
        self.assertEqual(self._bills().state, "draft")
        self.assertFalse(
            self.lines.filtered(lambda l: l.last_payment_date),
            "a DRAFT bill must never settle royalties")
