# -*- coding: utf-8 -*-
"""Special sales in the legacy base: the channel the royalties department
sets by hand, under the invoices' rule (special channel AND discount at or
above the minimum -> a contract on the cover price pays on the net).

Money by hand, on the contract's 7% tier. March 2005 is NF 2 alone: 30
copies, R$ 300,00 gross, R$ 240,00 net -- a 20% discount. On the cover
price that month pays 7% of R$ 300,00 = R$ 21,00; as a special sale, 7% of
R$ 240,00 = R$ 16,80."""
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import LegacyCase


@tagged("post_install", "-at_install", "copyright_legacy")
class TestLegacySpecialSales(LegacyCase):
    def setUp(self):
        super().setUp()
        self.Sale._import_file(self.write_csv(self.SAMPLE))
        self.contract.legacy_enabled = True
        self.royalty.on_sales_price = True
        Team = self.env["crm.team"]
        self.special_team = Team.create({"name": "Vendas especiais (teste)"})
        self.other_team = Team.create({"name": "Livrarias (teste)"})
        self.company = self.contract.company_id
        self.company.write({
            "contract_special_sales_team_ids": [(6, 0, self.special_team.ids)],
            "contract_special_min_discount": 15.0,
        })
        self.nf2 = self.Sale.search([("nf", "=", "2")])

    def march_amount(self):
        self.royalty._edlab_book_legacy()
        return self.legacy_lines()[0].amount

    def test_discount_percent_from_net_and_gross(self):
        self.assertEqual(self.nf2.discount_percent, 20.0)
        nf4 = self.Sale.search([("nf", "=", "4")])
        self.assertEqual(nf4.discount_percent, 0.0)
        # NF 5 has no gross: nothing to compare with, no discount.
        nf5 = self.Sale.search([("nf", "=", "5")])
        self.assertEqual(nf5.discount_percent, 0.0)

    def test_special_channel_pays_on_the_net(self):
        self.nf2.team_id = self.special_team
        self.assertTrue(self.nf2.special_sale)
        self.assertAlmostEqual(self.march_amount(), -16.80, places=2)
        self.assertEqual(self.legacy_lines()[0].edlab_legacy_base, 240.0)

    def test_without_channel_stays_on_the_cover_price(self):
        self.assertFalse(self.nf2.special_sale)
        self.assertAlmostEqual(self.march_amount(), -21.0, places=2)

    def test_discount_below_the_minimum_is_not_special(self):
        self.company.contract_special_min_discount = 25.0
        self.nf2.team_id = self.special_team
        self.assertFalse(self.nf2.special_sale)
        self.assertAlmostEqual(self.march_amount(), -21.0, places=2)

    def test_ordinary_channel_is_not_special(self):
        self.nf2.team_id = self.other_team
        self.assertFalse(self.nf2.special_sale)
        self.assertAlmostEqual(self.march_amount(), -21.0, places=2)

    def test_no_special_channel_configured_nothing_is_special(self):
        self.nf2.team_id = self.special_team
        self.company.contract_special_sales_team_ids = [(5, 0, 0)]
        self.assertFalse(self.nf2.special_sale)
        self.assertAlmostEqual(self.march_amount(), -21.0, places=2)

    def test_contract_on_net_is_untouched(self):
        self.royalty.on_sales_price = False
        self.nf2.team_id = self.special_team
        self.assertAlmostEqual(self.march_amount(), -16.80, places=2)

    def test_marking_refreshes_an_existing_booking(self):
        self.assertAlmostEqual(self.march_amount(), -21.0, places=2)
        self.nf2.team_id = self.special_team
        created, updated, _removed = self.royalty._edlab_book_legacy()
        self.assertEqual((created, updated), (0, 1))
        self.assertAlmostEqual(self.legacy_lines()[0].amount, -16.80, places=2)

    def test_search_special_and_without_channel(self):
        self.nf2.team_id = self.special_team
        self.assertEqual(self.Sale.search([("special_sale", "=", True)]), self.nf2)
        not_special = self.Sale.search([("special_sale", "!=", True)])
        self.assertNotIn(self.nf2, not_special)
        # Rows with no channel at all are "not special", not left out.
        self.assertEqual(len(not_special), len(self.Sale.search([])) - 1)
        self.assertNotIn(self.nf2, self.Sale.search([("team_id", "=", False)]))

    def test_search_special_unsupported_operator(self):
        with self.assertRaises(UserError):
            # Odoo 19 refuses ilike on a boolean before reaching the method;
            # the method still guards itself for a direct call.
            self.Sale._search_special_sale("ilike", "x")

    def test_channel_edit_keeps_the_classification(self):
        before = (self.nf2.counts, self.nf2.royalty_base, self.nf2.royalty_base_gross)
        self.nf2.team_id = self.special_team
        self.assertEqual(
            (self.nf2.counts, self.nf2.royalty_base, self.nf2.royalty_base_gross),
            before)
