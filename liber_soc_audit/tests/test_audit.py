# -*- coding: utf-8 -*-
"""Tests for the XML-vs-Map audit: fiscal aggregation per CFOP effect,
the quality buckets that keep silent gaps visible, and the adjustment that
materializes an accepted divergence on the shelf.

Panels are created directly (no XML file): the audit reads already-parsed
``nfe.xml.panel`` rows and never re-parses, so tests seed the parsed shape.
"""
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

KEY_BASE = "352601112223330001815500100000%05d1000001236"


@tagged("post_install", "-at_install", "soc_audit")
class TestConsignmentAudit(TransactionCase):
    _key_seq = 0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.product = cls.env["product.product"].create({
            "name": "Iracema", "type": "consu",
            "is_storable": True, "standard_price": 20.0})
        partner = cls.env["res.partner"].create({
            "name": "Livraria Auditada", "is_company": True})
        cls.agreement = cls.env["consignment.agreement"].create({
            "partner_id": partner.id,
            "company_id": cls.company.id,
            "date_start": fields.Date.today(),
        })
        cls.agreement.action_activate()
        cls.partner = partner
        cls.cfop_ship = cls.env["nfe.cfop"].create({
            "code": "5917.T", "name": "Remessa consignação (teste)",
            "consignment_effect": "ship"})
        cls.cfop_sale = cls.env["nfe.cfop"].create({
            "code": "5113.T", "name": "Venda consignação (teste)",
            "consignment_effect": "sale"})
        cls.cfop_return = cls.env["nfe.cfop"].create({
            "code": "5918.T", "name": "Retorno consignação (teste)",
            "consignment_effect": "return"})

    def _panel(self, cfop, qty, product=None, cancelled=False):
        type(self)._key_seq += 1
        return self.env["nfe.xml.panel"].create({
            "key": KEY_BASE % self._key_seq,
            "partner_id": self.partner.id,
            "company_id": self.company.id,
            "cfop_id": cfop.id if cfop else False,
            "is_cancelled": cancelled,
            "file_create_date": fields.Date.today(),
            "status": "valid",
            "panel_items": [(0, 0, {
                "ks_product_id": (product or self.product).id,
                "ks_product_qty": qty,
            })],
        })

    def _audit(self):
        return self.env["consignment.audit"].create({
            "partner_id": self.partner.id,
            "company_id": self.company.id,
        })

    def test_reconciliation_math(self):
        """expected = opening + shipped - sold - returned (opening = 0 here)."""
        self._panel(self.cfop_ship, 10)
        self._panel(self.cfop_sale, 3)
        self._panel(self.cfop_return, 1)
        # shelf map: 4 on hand
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.agreement.location_id, 4)

        audit = self._audit()
        audit.action_compute()
        self.assertEqual(audit.state, "computed")
        line = audit.line_ids.filtered(
            lambda l: l.product_id == self.product)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.qty_shipped_xml, 10)
        self.assertEqual(line.qty_sold_xml, 3)
        self.assertEqual(line.qty_returned_xml, 1)
        self.assertEqual(line.qty_expected, 6)
        self.assertEqual(line.qty_map, 4)
        self.assertEqual(line.qty_diff, 2)
        self.assertEqual(line.line_state, "divergent")

    def test_quality_buckets(self):
        """Nothing is dropped silently: each anomaly lands in a counter."""
        self._panel(self.cfop_ship, 5)                      # counted
        self._panel(self.cfop_ship, 7, cancelled=True)      # excluded
        unmapped = self.env["nfe.cfop"].create({
            "code": "5999.T", "name": "Sem efeito (teste)"})
        self._panel(unmapped, 2)                            # unmapped cfop
        self._panel(None, 3)                                # no cfop at all
        orphan = self._panel(self.cfop_sale, 0)             # unmatched item
        orphan.panel_items.write({"ks_product_id": False, "ks_product_qty": 9})

        audit = self._audit()
        audit.action_compute()
        self.assertEqual(audit.panel_count, 2,
                         "counted: the ship panel and the orphan sale panel")
        self.assertEqual(audit.unmatched_item_count, 1)
        self.assertEqual(audit.no_cfop_panel_count, 1)
        self.assertIn(unmapped, audit.unmapped_cfop_ids)

    def test_accept_requires_resolution_then_adjusts_shelf(self):
        """Accepting the fiscal number materializes the divergence on the
        shelf through an adjustment consignment.move."""
        self._panel(self.cfop_ship, 10)
        self._panel(self.cfop_sale, 3)
        self._panel(self.cfop_return, 1)
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.agreement.location_id, 4)

        audit = self._audit()
        audit.action_compute()
        # unresolved divergence -> refuse to accept
        with self.assertRaises(UserError):
            audit.action_accept()

        audit.action_accept_all_fiscal()
        audit.action_accept()
        self.assertEqual(audit.state, "accepted")
        adjustment = self.env["consignment.move"].search([
            ("audit_id", "=", audit.id), ("move_kind", "=", "adjustment")])
        self.assertEqual(len(adjustment), 1)
        self.assertEqual(adjustment.state, "done")
        # the shelf now matches the accepted fiscal expectation (4 -> 6)
        self.assertEqual(self.agreement.on_shelf_qty, 6)
        # a computed-again audit is blocked once accepted
        with self.assertRaises(UserError):
            audit.action_compute()
