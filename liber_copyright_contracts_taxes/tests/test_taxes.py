# -*- coding: utf-8 -*-
"""Tests for the IRRF progressive table (Lei 15.270/2025 values shipped in
data/irrf_table_2026.xml) and the per-beneficiary mode dispatch.

Every expected value is hand-computed from the official 2026 numbers:
simplified discount 607,20; exemption up to 5.000,00; reducer
max(978,62 - 0,133145 x income, 0) applied up to 7.350,00."""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "copyright_taxes")
class TestIrrfTable(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.table = cls.env.ref("liber_copyright_contracts_taxes.irrf_table_2026")

    def test_exempt_below_withholding_limit(self):
        self.assertEqual(self.table._tax_for_income(4000.00), 0.0)
        self.assertEqual(self.table._tax_for_income(5000.00), 0.0)

    def test_mid_income_gets_table_minus_reducer(self):
        # income 6.000,00: base 5.392,80 -> 27,5% - 908,73 = 574,29
        # reducer (income <= 7.350): 978,62 - 0,133145x6000 = 179,75
        # tax = 574,29 - 179,75 = 394,54
        self.assertAlmostEqual(
            self.table._tax_for_income(6000.00), 394.54, places=2)

    def test_high_income_gets_no_reducer(self):
        # income 10.000,00: base 9.392,80 -> 27,5% - 908,73 = 1.674,29
        # above the reducer cap (7.350,00): no reducer
        self.assertAlmostEqual(
            self.table._tax_for_income(10000.00), 1674.29, places=2)

    def test_tax_never_negative(self):
        # just above the exemption: table result would be negative -> floor 0
        self.assertEqual(self.table._tax_for_income(5000.01), 0.0)

    def test_mode_dispatch(self):
        Table = self.env["edlab.irrf.table"]
        partner = self.env["res.partner"].create({"name": "Beneficiário X"})

        partner.edlab_irrf_mode = "none"
        self.assertEqual(Table._irrf_for_partner(partner, 6000.00), 0.0)

        partner.edlab_irrf_mode = "manual"
        partner.edlab_irrf_percentage = 10.0
        self.assertAlmostEqual(
            Table._irrf_for_partner(partner, 500.00), 50.0, places=2)

        partner.edlab_irrf_mode = "table"
        self.assertAlmostEqual(
            Table._irrf_for_partner(partner, 6000.00), 394.54, places=2)

        # income <= 0 never withholds, whatever the mode
        self.assertEqual(Table._irrf_for_partner(partner, 0.0), 0.0)
        self.assertEqual(Table._irrf_for_partner(partner, -10.0), 0.0)

    def test_table_for_date_picks_most_recent(self):
        table = self.env["edlab.irrf.table"]._table_for_date("2026-06-15")
        self.assertEqual(table, self.table)
