# -*- coding: utf-8 -*-
"""Stage 3 of the mailed statement: the document speaks the beneficiary's
language and, when a rate exists, counts in the beneficiary's currency."""
from datetime import date

from odoo.tests import tagged

from .test_reports import TestRoyaltyStatement


@tagged("post_install", "-at_install", "copyright_reports")
class TestStatementLanguage(TestRoyaltyStatement):
    allow_inherited_tests_method = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("pt_BR")
        cls.author.write({"street": "Rua A, 1", "city": "Rio", "zip": "20000-000"})
        # The testing company counts in USD: the foreign currency of the
        # tests is the euro, whatever the company's own is.
        assert cls.env.company.currency_id != cls.env.ref("base.EUR")
        cls._sell_and_book(cls(), 10)

    def _html(self):
        return self.env["ir.actions.report"]._render_qweb_html(
            "liber_copyright_contracts_reports.report_royalty_statement",
            self.author.ids)[0].decode()

    def test_english_beneficiary_reads_english(self):
        self.author.lang = "en_US"
        html = self._html()
        self.assertIn("Royalty statement", html)
        self.assertIn(">summary<", html)
        self.assertIn("Copies sold", html)
        self.assertIn("since the beginning", html)
        self.assertNotIn("Prestação de contas", html)
        st = self.author.with_context(lang="en_US")._edlab_royalty_statement()
        self.assertEqual(st["lang"], "en_US")
        self.assertRegex(st["today_label"], r"^[A-Z][a-z]+ \d{1,2}, \d{4}$")

    def test_brazilian_beneficiary_reads_portuguese_whatever_the_user(self):
        self.author.lang = "pt_BR"
        html = self.env["ir.actions.report"].with_context(lang="en_US")._render_qweb_html(
            "liber_copyright_contracts_reports.report_royalty_statement",
            self.author.ids)[0].decode()
        self.assertIn("Prestação de contas de direitos autorais", html)
        self.assertIn(">resumo<", html)
        self.assertIn("Livros vendidos", html)
        self.assertIn("desde o início", html)
        st = self.author.with_context(lang="pt_BR")._edlab_royalty_statement()
        self.assertRegex(st["today_label"], r"^\d{1,2} de [a-zç]+ de \d{4}$")

    def test_no_rate_keeps_company_currency_and_says_so(self):
        eur = self.env.ref("base.EUR")
        eur.rate_ids.unlink()
        self.author.edlab_beneficiary_currency_id = eur
        st = self.author._edlab_royalty_statement()
        self.assertEqual(st["currency"], self.env.company.currency_id)
        self.assertIn("no exchange rate", st["fx_note"])
        self.assertIn("no exchange rate", self._html())

    def test_rate_converts_every_amount(self):
        eur = self.env.ref("base.EUR")
        eur.rate_ids.unlink()
        company_currency = self.env.company.currency_id
        # 1 company unit = 0.2 EUR on this date (rate is expressed against
        # the company currency).
        self.env["res.currency.rate"].create({
            "currency_id": eur.id, "name": date(2020, 1, 1), "rate": 0.2,
            "company_id": self.env.company.id})
        before = self.author._edlab_royalty_statement()
        self.author.edlab_beneficiary_currency_id = eur
        st = self.author._edlab_royalty_statement()
        self.assertEqual(st["currency"], eur)
        self.assertAlmostEqual(st["accrued"], eur.round(before["accrued"] * 0.2), places=2)
        self.assertAlmostEqual(st["rows"][0]["amount"],
                               eur.round(before["rows"][0]["amount"] * 0.2), places=2)
        self.assertAlmostEqual(st["net"], eur.round(before["net"] * 0.2), places=2)
        self.assertIn("converted from %s to EUR" % company_currency.name, st["fx_note"])
        self.assertIn("1 %s = 0.2000 EUR" % company_currency.name, st["fx_note"])
        html = self._html()
        self.assertIn("converted from", html)
