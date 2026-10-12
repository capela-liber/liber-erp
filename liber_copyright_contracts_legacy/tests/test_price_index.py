# -*- coding: utf-8 -*-
"""The compounding convention, stated in the module docstring, pinned here
with hand-computed numbers: 1% then 2% is x1.0302, not x1.03."""
from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.liber_copyright_contracts_legacy.models.price_index import (
    compounding_factor)


@tagged("post_install", "-at_install", "copyright_legacy")
class TestPriceIndex(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.index = cls.env["edlab.price.index"].create({
            "name": "Teste", "code": "TST", "bcb_series": 999})
        cls.Value = cls.env["edlab.price.index.value"]
        for month, pct in ((1, 1.0), (2, 2.0), (3, 0.5)):
            cls.Value.create({"index_id": cls.index.id,
                              "date": date(2020, month, 1), "variation": pct})

    def test_pure_factor_excludes_start_month_includes_end(self):
        v = {date(2020, 1, 1): 1.0, date(2020, 2, 1): 2.0, date(2020, 3, 1): 0.5}
        self.assertAlmostEqual(
            compounding_factor(v, date(2020, 1, 15), date(2020, 3, 1)),
            1.02 * 1.005, places=9)
        self.assertEqual(compounding_factor(v, date(2020, 3, 1), date(2020, 3, 31)), 1.0)
        # Never deflates: a reference before the sale is a factor of one.
        self.assertEqual(compounding_factor(v, date(2020, 3, 1), date(2020, 1, 1)), 1.0)

    def test_pure_factor_names_the_missing_month(self):
        v = {date(2020, 1, 1): 1.0, date(2020, 3, 1): 0.5}
        with self.assertRaises(KeyError) as caught:
            compounding_factor(v, date(2020, 1, 1), date(2020, 3, 1))
        self.assertEqual(caught.exception.args[0], date(2020, 2, 1))

    def test_model_factor_and_bounds(self):
        self.assertEqual(self.index.first_date, date(2020, 1, 1))
        self.assertEqual(self.index.last_date, date(2020, 3, 1))
        self.assertEqual(self.index.value_count, 3)
        self.assertAlmostEqual(
            self.index.factor(date(2020, 1, 20), date(2020, 3, 5)), 1.02 * 1.005)

    def test_model_factor_missing_month_is_a_user_error(self):
        with self.assertRaises(UserError) as caught:
            self.index.factor(date(2020, 1, 1), date(2020, 6, 1))
        self.assertIn("04/2020", str(caught.exception))

    @mute_logger("odoo.sql_db")
    def test_value_date_snaps_to_month_start_and_is_unique(self):
        value = self.Value.create({"index_id": self.index.id,
                                   "date": date(2020, 4, 17), "variation": 0.1})
        self.assertEqual(value.date, date(2020, 4, 1))
        with self.assertRaises(Exception), self.cr.savepoint():
            self.Value.create({"index_id": self.index.id,
                               "date": date(2020, 4, 2), "variation": 0.2})

    def test_shipped_ipca_is_real_data(self):
        """The IPCA shipped with the module is the IBGE series: Jan/1999 was
        0.70% and the table runs past 2025."""
        ipca = self.env.ref("liber_copyright_contracts_legacy.price_index_ipca")
        jan99 = ipca.value_ids.filtered(lambda v: v.date == date(1999, 1, 1))
        self.assertEqual(jan99.variation, 0.70)
        self.assertGreaterEqual(ipca.last_date, date(2026, 1, 1))
        self.assertGreater(ipca.factor(date(1999, 1, 1), date(2025, 12, 1)), 4.0)

    def test_fetch_bcb_upserts(self):
        payload = [{"data": "01/03/2020", "valor": "0.60"},   # revised
                   {"data": "01/04/2020", "valor": "0,30"},   # new, comma
                   {"data": "garbage"}]
        fake = type("R", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: payload})()
        with patch("odoo.addons.liber_copyright_contracts_legacy.models."
                   "price_index.requests.get", return_value=fake) as get:
            self.index.action_fetch_bcb()
        self.assertIn("bcdata.sgs.999", get.call_args[0][0])
        by_month = {v.date: v.variation for v in self.index.value_ids}
        self.assertEqual(by_month[date(2020, 3, 1)], 0.60)
        self.assertEqual(by_month[date(2020, 4, 1)], 0.30)
        self.assertEqual(len(by_month), 4)

    def test_fetch_bcb_without_series_refuses(self):
        self.index.bcb_series = 0
        with self.assertRaises(UserError):
            self.index.action_fetch_bcb()
