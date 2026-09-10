# -*- coding: utf-8 -*-
"""The link both ways: the source counts its mirror and opens it; the mirror
knows its source and opens it; a document without a pair shows nothing."""
from odoo.tests import TransactionCase, tagged

from .common import MirrorFixture


@tagged("post_install", "-at_install", "intercompany_mirror")
class TestMirrorLink(MirrorFixture, TransactionCase):

    def setUp(self):
        super().setUp()
        self.source, self.dest = self._two_companies()
        self.product = self._wire(self.source, self.dest)

    def test_source_sees_its_mirror(self):
        invoice, mirror = self._post_pair(self.source, self.dest, self.product)
        self.assertEqual(len(mirror), 1, "the OCA module must create the mirror")
        self.assertEqual(invoice.mirror_count, 1)
        self.assertEqual(invoice.mirror_move_ids, mirror)
        action = invoice.action_open_mirror()
        self.assertEqual(action["res_model"], "account.move")
        self.assertEqual(action["res_id"], mirror.id)
        self.assertEqual(action["view_mode"], "form")

    def test_mirror_sees_its_source(self):
        invoice, mirror = self._post_pair(self.source, self.dest, self.product)
        self.assertEqual(mirror.sudo().auto_invoice_id, invoice)
        self.assertEqual(mirror.mirror_count, 0, "the mirror has no mirror of its own")
        action = mirror.sudo().action_open_mirror_source()
        self.assertEqual(action["res_id"], invoice.id)

    def test_document_without_pair_shows_nothing(self):
        customer = self.env["res.partner"].create({"name": "Plain Customer"})
        invoice = self.env["account.move"].with_company(self.source).create({
            "move_type": "out_invoice",
            "company_id": self.source.id,
            "partner_id": customer.id,
            "invoice_line_ids": [(0, 0, {
                "product_id": self.product.id, "quantity": 1, "price_unit": 10.0})],
        })
        invoice.action_post()
        self.assertEqual(invoice.mirror_count, 0)
        self.assertFalse(invoice.auto_invoice_id)
        # opening "the mirror" of a document that has none yields an empty list,
        # never an error: the button is hidden anyway
        action = invoice.action_open_mirror()
        self.assertEqual(action["domain"], [("id", "in", [])])
