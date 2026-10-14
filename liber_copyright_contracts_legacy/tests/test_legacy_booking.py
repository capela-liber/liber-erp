# -*- coding: utf-8 -*-
"""The contract side: one analytic entry per month, the tier on the running
total, the price-index correction, idempotency with refresh, the removal,
and the legacy copies opening the running total of the invoiced sales.

Money is hand-computed. March 2005: 30 copies, R$ 240,00 net, tier 7% ->
R$ 16,80 nominal. April: 90 more copies push the total to 120 -> 8% on
R$ 740,00 = R$ 59,20. May: the return of 5 copies, -R$ 50,00 x 8% =
-R$ 4,00. June: 4 copies, R$ 40,00 x 8% = R$ 3,20."""
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import LegacyCase


@tagged("post_install", "-at_install", "copyright_legacy")
class TestLegacyBooking(LegacyCase):
    def setUp(self):
        super().setUp()
        self.Sale._import_file(self.write_csv(self.SAMPLE))
        self.contract.legacy_enabled = True

    def _invoice(self, qty, price=10.0):
        customer = self.env["res.partner"].create({"name": "Livraria"})
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": customer.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [(0, 0, {
                "product_id": self.book.product_variant_id.id,
                "quantity": qty, "price_unit": price})],
        })
        move.action_post()
        return move

    def test_nominal_booking_one_entry_per_month(self):
        created, updated, removed = self.royalty._edlab_book_legacy()
        self.assertEqual((created, updated, removed), (4, 0, 0))
        lines = self.legacy_lines()
        self.assertEqual(lines.mapped("edlab_legacy_period"),
                         ["2005-03", "2005-04", "2005-05", "2005-06"])
        self.assertEqual(lines.mapped("date"),
                         [date(2005, 3, 31), date(2005, 4, 30),
                          date(2005, 5, 31), date(2005, 6, 30)])
        self.assertEqual([round(a, 2) for a in lines.mapped("amount")],
                         [-16.80, -59.20, 4.00, -3.20])
        self.assertEqual(lines.mapped("edlab_royalty_percentage"), [7.0, 8.0, 8.0, 8.0])
        self.assertEqual(lines.mapped("unit_amount"), [30, 90, -5, 4])
        self.assertTrue(all(f == 1.0 for f in lines.mapped("edlab_legacy_factor")))
        self.assertEqual(lines.mapped("account_id"), self.account)
        self.assertEqual(lines.partner_id, self.author)
        self.assertAlmostEqual(self.contract.legacy_accrued, 75.20, places=2)
        self.assertEqual(self.contract.legacy_qty, 119)
        self.assertEqual(self.contract.legacy_base, 970.0)

    def test_gross_base_when_on_sales_price(self):
        self.royalty.on_sales_price = True
        self.royalty._edlab_book_legacy()
        march = self.legacy_lines()[0]
        # 30 copies x R$ 10,00 cover = R$ 300,00 x 7% = R$ 21,00
        self.assertAlmostEqual(march.amount, -21.0, places=2)
        self.assertEqual(march.edlab_legacy_base, 300.0)

    def test_index_corrects_each_month_to_the_reference(self):
        self.contract.write({"legacy_index_id": self.ipca.id,
                             "legacy_reference_date": date(2005, 6, 1)})
        self.royalty._edlab_book_legacy()
        lines = self.legacy_lines()
        f_march = self.ipca.factor(date(2005, 3, 1), date(2005, 6, 1))
        f_june = self.ipca.factor(date(2005, 6, 1), date(2005, 6, 1))
        self.assertGreater(f_march, 1.0)
        self.assertEqual(f_june, 1.0)
        self.assertAlmostEqual(lines[0].edlab_legacy_factor, f_march, places=6)
        self.assertAlmostEqual(lines[0].amount, -240.0 * f_march * 0.07, places=2)
        self.assertAlmostEqual(lines[3].amount, -3.20, places=2)
        self.assertIn("IPCA", lines[0].name)

    def test_reference_defaults_to_the_last_month_of_the_index(self):
        self.contract.legacy_index_id = self.ipca
        self.assertEqual(self.contract._edlab_legacy_reference_date(),
                         self.ipca.last_date)
        self.royalty._edlab_book_legacy()
        # Twenty years of IPCA at least double the money.
        self.assertGreater(self.legacy_lines()[0].edlab_legacy_factor, 2.0)

    def test_reference_without_index_is_refused(self):
        with self.assertRaises(ValidationError):
            self.contract.legacy_reference_date = date(2020, 1, 1)

    def test_missing_index_month_stops_the_booking(self):
        empty = self.env["edlab.price.index"].create({"name": "Vazio", "code": "VZ"})
        self.contract.legacy_index_id = empty
        with self.assertRaises(UserError):
            self.contract.action_book_legacy()
        self.env["edlab.price.index.value"].create({
            "index_id": empty.id, "date": date(2005, 6, 1), "variation": 1.0})
        with self.assertRaises(UserError) as caught:
            self.contract.action_book_legacy()
        self.assertIn("04/2005", str(caught.exception))

    def test_rerun_is_idempotent_and_refreshes(self):
        self.royalty._edlab_book_legacy()
        self.assertEqual(self.royalty._edlab_book_legacy(), (0, 0, 0))
        # The department fixes a row: the month's entry follows.
        april_sale = self.Sale.search([("nf", "=", "4")])
        april_sale.force_exclude = True
        created, updated, removed = self.royalty._edlab_book_legacy()
        self.assertEqual((created, updated, removed), (0, 1, 0))
        april = self.legacy_lines()[1]
        # 80 copies, R$ 640,00; running total 110 -> still 8%: R$ 51,20
        self.assertAlmostEqual(april.amount, -51.20, places=2)
        self.assertEqual(april.unit_amount, 80)
        # A month that disappears loses its entry.
        self.Sale.search([("nf", "=", "8")]).write({"force_exclude": True})
        self.assertEqual(self.royalty._edlab_book_legacy(), (0, 0, 1))
        self.assertEqual(len(self.legacy_lines()), 3)

    def test_window_limits_the_months(self):
        self.contract.legacy_date_from = date(2005, 5, 1)
        self.royalty._edlab_book_legacy()
        lines = self.legacy_lines()
        self.assertEqual(lines.mapped("edlab_legacy_period"), ["2005-05", "2005-06"])
        # The running total restarts inside the window: -5 then -1, clamped
        # at zero for the lookup -> first tier, 7%.
        self.assertEqual(lines.mapped("edlab_royalty_percentage"), [7.0, 7.0])

    def test_disabled_contract_books_nothing_and_unbook_cleans(self):
        self.royalty._edlab_book_legacy()
        self.assertEqual(len(self.legacy_lines()), 4)
        self.contract.action_unbook_legacy()
        self.assertFalse(self.legacy_lines())
        self.contract.legacy_enabled = False
        self.assertEqual(self.royalty._edlab_book_legacy(), (0, 0, 0))
        with self.assertRaises(UserError):
            self.contract.action_book_legacy()

    def test_no_tier_books_nothing(self):
        self.royalty.tier_ids.unlink()
        self.assertEqual(self.royalty._edlab_book_legacy(), (0, 0, 0))

    def test_cancelled_contract_books_nothing(self):
        self.contract.sudo().write({"state": "cancelled"})
        self.assertEqual(self.royalty._edlab_book_legacy(), (0, 0, 0))

    def test_legacy_copies_open_the_running_total_of_invoices(self):
        """119 legacy copies: the FIRST invoice here is already at 8%."""
        self.assertEqual(self.royalty._edlab_initial_cumulative_qty(), 119)
        invoice = self._invoice(10)   # R$ 100,00
        # The engine's booking method takes the invoices it is given; the
        # contract button would only hand it PAID ones.
        self.royalty._book_royalties_from_invoices(invoice)
        accrual = self.env["account.analytic.line"].search(
            [("edlab_source_move_line_id", "in", invoice.invoice_line_ids.ids)])
        self.assertEqual(len(accrual), 1)
        self.assertEqual(accrual.edlab_royalty_percentage, 8.0)
        self.assertAlmostEqual(accrual.amount, -8.0, places=2)
        # The contract button books the legacy months in the same run.
        self.contract.action_fill_royalty_lines()
        self.assertEqual(len(self.legacy_lines()), 4)
        # Switched off, the counter opens at zero again: 10 copies -> 7%.
        self.contract.legacy_enabled = False
        self.assertEqual(self.royalty._edlab_initial_cumulative_qty(), 0)

    def test_legacy_entries_are_accruals_for_the_cutoff_and_statement(self):
        self.royalty._edlab_book_legacy()
        domain = self.royalty._edlab_accrual_entry_domain()
        entries = self.env["account.analytic.line"].search(domain)
        self.assertEqual(len(entries), 4)
        # A payment on 2005-04-30 settles March and April: cutoff of 76,00.
        self.royalty.sudo().last_payment_date = date(2005, 4, 30)
        self.royalty._book_royalties_from_invoices(self.env["account.move"])
        cutoff = self.env["account.analytic.line"].search(
            [("edlab_payment_cutoff_line_id", "=", self.royalty.id)])
        self.assertAlmostEqual(cutoff.amount, 76.0, places=2)

    def test_smart_button_action_filters_the_works(self):
        action = self.contract.action_view_legacy_sales()
        self.assertEqual(action["domain"], [("product_tmpl_id", "in", [self.book.id])])
        self.assertEqual(self.contract.legacy_sale_count, 9)

    def test_user_without_manager_cannot_edit_rows(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Leitor", "login": "legacy_reader",
            "group_ids": [(6, 0, [self.env.ref(
                "liber_copyright_contracts.group_contract_user").id])]})
        sale = self.Sale.search([("nf", "=", "2")])
        self.assertEqual(sale.with_user(user).title, "Dom Casmurro")
        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError):
            sale.with_user(user).write({"force_exclude": True})


@tagged("post_install", "-at_install", "copyright_legacy")
class TestLegacyStatement(LegacyCase):
    """The author's statement shows the correction per year."""

    def setUp(self):
        super().setUp()
        from .common import row
        extra = [row(nf="50", data_emissao="2006-02-10", quantidade="10", cfop="5101",
                     natureza_operacao="VENDA (produção própria)",
                     valor_liquido="100.0", valor_liquido_estimado="100.0")]
        self.Sale._import_file(self.write_csv(self.SAMPLE + extra))
        self.contract.write({"legacy_enabled": True, "legacy_index_id": self.ipca.id,
                             "legacy_reference_date": date(2006, 12, 1)})
        self.royalty._edlab_book_legacy()

    def test_year_rows_carry_nominal_corrected_and_factor(self):
        st = self.author._edlab_royalty_statement()
        rows = st["legacy_years"]
        self.assertEqual([r["year"] for r in rows], [2005, 2006])
        r2005, r2006 = rows
        self.assertEqual(r2005["qty"], 119)
        self.assertEqual(r2005["nominal"], 970.0)
        self.assertGreater(r2005["factor"], 1.0)
        self.assertAlmostEqual(r2005["corrected"], 970.0 * r2005["factor"], places=1)
        self.assertEqual(r2005["percentage_label"], "7,00 a 8,00%")
        self.assertEqual(r2005["index_label"], "IPCA 12/2006")
        self.assertEqual(r2006["qty"], 10)
        self.assertEqual(r2006["nominal"], 100.0)
        self.assertEqual(r2006["percentage_label"], "8,00%")
        # The year rows add up to the legacy part of the statement total.
        total = st["legacy_years_total"]
        self.assertAlmostEqual(total["amount"], self.contract.legacy_accrued, places=2)
        self.assertAlmostEqual(total["amount"], st["accrued"], places=2)
        self.assertEqual(total["qty"], 129)

    def test_statement_after_payment_hides_settled_years(self):
        self.royalty.sudo().last_payment_date = date(2005, 12, 31)
        st = self.author._edlab_royalty_statement()
        self.assertEqual([r["year"] for r in st["legacy_years"]], [2006])

    def test_nominal_contract_shows_dash_and_factor_one(self):
        self.contract.write({"legacy_index_id": False, "legacy_reference_date": False})
        self.royalty._edlab_book_legacy()
        rows = self.author._edlab_royalty_statement()["legacy_years"]
        self.assertEqual(rows[0]["index_label"], "\N{EM DASH}")
        self.assertEqual(rows[0]["factor_label"], "1,0000")
        self.assertEqual(rows[0]["corrected"], rows[0]["nominal"])

    def test_report_renders_the_yearly_table(self):
        html = self.env["ir.actions.report"]._render_qweb_html(
            "liber_copyright_contracts_reports.report_royalty_statement",
            self.author.ids)[0].decode()
        self.assertIn("monetary correction by year", html)
        self.assertIn("IPCA 12/2006", html)
        self.assertIn("2006", html)

    def test_no_legacy_no_table(self):
        self.contract.action_unbook_legacy()
        st = self.author._edlab_royalty_statement()
        self.assertEqual(st["legacy_years"], [])
        html = self.env["ir.actions.report"]._render_qweb_html(
            "liber_copyright_contracts_reports.report_royalty_statement",
            self.author.ids)[0].decode()
        self.assertNotIn("monetary correction by year", html)
