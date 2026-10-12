# -*- coding: utf-8 -*-
"""Import and classification: the CSV lands through COPY, the ISBN finds the
product, the CFOP decides the effect, the flags decide the exclusion, and a
hand edit re-runs the same rules on that row."""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import HEADER, ISBN, LegacyCase, row
from odoo.addons.liber_copyright_contracts_legacy.models.legacy_cfop import (
    effect_from_nature)


@tagged("post_install", "-at_install", "copyright_legacy")
class TestLegacyImport(LegacyCase):
    def setUp(self):
        super().setUp()
        self.total = self.Sale._import_file(self.write_csv(self.SAMPLE))
        self.by_nf = {}
        for sale in self.Sale.search([]):
            self.by_nf.setdefault(sale.nf, []).append(sale)

    def one(self, nf):
        return self.by_nf[nf][0]

    def test_rows_land_with_casts(self):
        self.assertEqual(self.total, 10)
        s = self.one("2")
        self.assertEqual(s.date, date(2005, 3, 20))
        self.assertEqual((s.year, s.month), (2005, 3))
        self.assertEqual(s.quantity, 30)
        self.assertEqual(s.amount_net_estimated, 240.0)
        self.assertEqual(s.cfop, "5113")
        self.assertEqual(s.company_id, self.env.company)
        # Empty cells are unknown, not zero: the shipment had no cover price.
        self.assertFalse(self.one("1").list_price)

    def test_isbn_links_the_product(self):
        self.assertEqual(self.one("2").product_id, self.book.product_variant_id)
        self.assertEqual(self.one("2").product_tmpl_id, self.book)
        self.assertFalse(self.one("9").product_id)

    def test_cfop_decides_the_effect(self):
        self.assertEqual(self.one("1").effect, "neutral")   # 5917 shipment
        self.assertEqual(self.one("2").effect, "sale")      # 5113 settlement
        self.assertEqual(self.one("3").effect, "sale")      # 6113
        self.assertEqual(self.one("4").effect, "sale")      # 5101
        self.assertEqual(self.one("5").effect, "return")    # 1201
        self.assertEqual(self.one("6").effect, "courtesy")  # 5910
        self.assertEqual(self.one("2").cfop_id.code, "5113")

    def test_wording_classifies_a_row_without_cfop(self):
        self.assertFalse(self.one("8").cfop)
        self.assertEqual(self.one("8").effect, "sale")
        self.assertEqual(effect_from_nature("DEVOLUÇÃO de venda"), "return")
        self.assertEqual(effect_from_nature("REMESSA em consignação"), "neutral")
        self.assertEqual(effect_from_nature("DOAÇÃO / BRINDE"), "courtesy")
        self.assertEqual(effect_from_nature(None), "neutral")

    def test_flags_exclude_and_counts_follows(self):
        cancelled = self.one("7")
        self.assertTrue(cancelled.excluded)
        self.assertIn("Cancelled", cancelled.exclusion_reason)
        self.assertFalse(cancelled.counts)
        first, dup = sorted(self.by_nf["8"], key=lambda s: s.sequence)
        self.assertTrue(first.counts)
        self.assertTrue(dup.excluded)
        self.assertFalse(dup.counts)
        # Counting rows: the two settlements, the sale, the return, nf 8.
        counted = self.Sale.search([("counts", "=", True)])
        self.assertEqual(sorted(counted.mapped("nf")), ["2", "3", "4", "5", "8"])
        self.assertFalse(self.one("1").counts)   # shipment
        self.assertFalse(self.one("6").counts)   # donation
        self.assertFalse(self.one("9").counts)   # no product

    def test_signed_bases(self):
        self.assertEqual(self.one("5").signed_quantity, -5)
        self.assertEqual(self.one("5").royalty_base, -50.0)
        self.assertEqual(self.one("2").royalty_base, 240.0)
        self.assertEqual(self.one("2").royalty_base_gross, 300.0)
        # Gross falls back to the net when the source had no cover price.
        self.assertEqual(self.one("8").royalty_base_gross, 40.0)

    def test_manual_overrides_reclassify_the_row(self):
        shipment = self.one("1")
        shipment.effect_manual = "sale"
        self.assertEqual(shipment.effect, "sale")
        self.assertTrue(shipment.counts)
        shipment.force_exclude = True
        self.assertFalse(shipment.counts)
        cancelled = self.one("7")
        cancelled.force_include = True
        self.assertTrue(cancelled.counts)

    def test_linking_a_product_by_hand_makes_the_row_count(self):
        orphan = self.one("9")
        wizard = self.env["edlab.legacy.link.product"].with_context(
            active_ids=orphan.ids).create({"product_id": self.book.product_variant_id.id})
        wizard.action_link()
        self.assertEqual(orphan.product_id, self.book.product_variant_id)
        self.assertTrue(orphan.counts)

    def test_monthly_totals(self):
        rows = self.Sale._monthly_totals(self.book)
        self.assertEqual([r["month"] for r in rows],
                         [date(2005, 3, 1), date(2005, 4, 1),
                          date(2005, 5, 1), date(2005, 6, 1)])
        self.assertEqual(rows[0]["qty"], 30)
        self.assertEqual(rows[1], {"month": date(2005, 4, 1), "qty": 90,
                                   "base_net": 740.0, "base_gross": 900.0,
                                   # No company asked: no special sales, the
                                   # cover-price base is the gross.
                                   "base_sales_price": 900.0})
        self.assertEqual(rows[2]["qty"], -5)
        self.assertEqual(rows[2]["base_net"], -50.0)
        self.assertEqual(rows[3]["qty"], 4)
        bounded = self.Sale._monthly_totals(self.book, date_from=date(2005, 5, 1))
        self.assertEqual(len(bounded), 2)

    def test_replace_wipes_and_append_keeps(self):
        extra = [row(nf="99", data_emissao="2006-01-01", quantidade="1", cfop="5101",
                     natureza_operacao="VENDA", valor_liquido="10")]
        self.Sale._import_file(self.write_csv(extra), replace=False)
        self.assertEqual(self.Sale.search_count([]), 11)
        self.Sale._import_file(self.write_csv(extra), replace=True)
        self.assertEqual(self.Sale.search_count([]), 1)

    def test_wrong_header_is_refused(self):
        bad = self.write_csv([["x", "y"]], header=["fonte", "nf"])
        with self.assertRaises(UserError) as caught:
            self.Sale._import_file(bad)
        self.assertIn("data_emissao", str(caught.exception))
        with self.assertRaises(UserError):
            self.Sale._import_file("/nowhere/base.csv")

    def test_reclassify_after_cfop_change(self):
        cfop = self.env["edlab.legacy.cfop"].search([("code", "=", "5910")])
        cfop.effect = "sale"
        self.Sale.action_reclassify_all()
        self.assertEqual(self.one("6").effect, "sale")
        self.assertTrue(self.one("6").counts)

    @mute_logger("odoo.sql_db")
    def test_cfop_code_must_be_four_digits(self):
        with self.assertRaises(Exception), self.cr.savepoint():
            self.env["edlab.legacy.cfop"].create({"code": "51A1", "name": "x"})
