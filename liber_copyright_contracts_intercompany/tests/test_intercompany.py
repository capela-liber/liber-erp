# -*- coding: utf-8 -*-
"""Tests for the intercompany royalty charge: source-company stamping, the
draft accumulator pair, its idempotent recompute, the mirror bill born on
post, and the multi-company access path.

Money math is hand-computed (family convention): 80 copies x R$ 10,00 =
R$ 800,00 @ 7% -> R$ 56,00 accrued, so R$ 56,00 charged to the seller."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "copyright_intercompany")
class TestIntercompanyRoyalties(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.company_he = cls.env.company
        cls.company_el = cls.env["res.company"].create(
            {"name": "Edlab Press (interco test)"})
        cls.env["account.chart.template"].try_loading(
            cls.company_he.chart_template,
            company=cls.company_el,
            install_demo=False,
        )
        cls.env.user.company_ids |= cls.company_el
        cls.company_he.contract_interco_source_company_ids = cls.company_el

        cls.author = cls.env["res.partner"].create({"name": "Machado de Assis"})
        cls.customer = cls.env["res.partner"].create({"name": "Livraria Cliente"})
        cls.book = cls.env["product.template"].create({
            "name": "Dom Casmurro", "type": "consu", "list_price": 10.0})
        cls.contract = cls.env["edlab.contract"].create({
            "company_id": cls.company_he.id,
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [(0, 0, {
                "partner_id": cls.author.id,
                "product_id": cls.book.id,
                "tier_ids": [
                    (0, 0, {"qty_from": 0, "qty_to": 100, "percentage": 7.0}),
                    (0, 0, {"qty_from": 101, "qty_to": 0, "percentage": 8.0}),
                ],
            })],
        })
        cls.royalty = cls.contract.royalty_line_ids
        cls.royalty.action_create_analytic_account()
        cls.account = cls.royalty.analytic_account_id

    def _invoice(self, company, qty, price=10.0, days_ago=0):
        move = self.env["account.move"].with_company(company).create({
            "move_type": "out_invoice",
            "company_id": company.id,
            "partner_id": self.customer.id,
            "invoice_date": fields.Date.today() - timedelta(days=days_ago),
            "invoice_line_ids": [(0, 0, {
                "product_id": self.book.product_variant_id.id,
                "quantity": qty,
                "price_unit": price,
            })],
        })
        move.action_post()
        return move

    def _pay(self, move):
        self.env["account.payment.register"].with_company(
            move.company_id
        ).with_context(
            active_model="account.move", active_ids=move.ids
        ).create({}).action_create_payments()

    def _accruals(self):
        return self.env["account.analytic.line"].sudo().search([
            ("account_id", "=", self.account.id),
            ("edlab_source_move_line_id", "!=", False),
        ])

    def _pair_invoices(self, state=None):
        domain = [
            ("edlab_is_interco_invoice", "=", True),
            ("company_id", "=", self.company_he.id),
            ("edlab_interco_source_company_id", "=", self.company_el.id),
        ]
        if state:
            domain.append(("state", "=", state))
        return self.env["account.move"].sudo().search(domain, order="id")

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------
    def test_source_company_stamped(self):
        inv_el = self._invoice(self.company_el, 10, days_ago=2)
        inv_he = self._invoice(self.company_he, 5, days_ago=1)
        self.royalty._book_royalties_from_invoices(inv_el + inv_he)
        accruals = self._accruals()
        self.assertEqual(len(accruals), 2)
        by_source = {a.edlab_source_company_id: a for a in accruals}
        self.assertIn(self.company_el, by_source)
        self.assertIn(self.company_he, by_source)
        self.assertEqual(
            by_source[self.company_el].edlab_source_move_line_id.company_id,
            self.company_el)

    def test_post_with_only_the_holder_company_active(self):
        """Posting the pair invoice with ONLY the holder company active is
        the everyday click, and the seller-journal type guard must not turn
        into the crash it guards against (multi-company read rule on the
        other company's journal)."""
        journal = self.env["account.journal"].sudo().create({
            "name": "Compras EL", "code": "CEL", "type": "purchase",
            "company_id": self.company_el.id,
        })
        self.company_el.contract_interco_purchase_journal_id = journal
        inv_el = self._invoice(self.company_el, 10)
        self.royalty._book_royalties_from_invoices(inv_el)
        pair = self._pair_invoices("draft")
        self.assertEqual(len(pair), 1)

        admin = self.env.ref("base.user_admin")
        admin.company_ids |= self.company_he | self.company_el
        pair.with_user(admin).with_context(
            allowed_company_ids=[self.company_he.id]).action_post()
        self.assertEqual(pair.state, "posted")
        mirror = self.env["account.move"].sudo().search(
            [("edlab_interco_mirror_move_id", "=", pair.id)])
        self.assertEqual(len(mirror), 1)
        self.assertEqual(mirror.journal_id, journal)

    def test_source_company_groups_the_debt_report(self):
        """The Royalty Debts report reads the collaboration: grouping by
        Source Company must split the sister company's sales from the house's
        own -- one group each, with the right totals."""
        inv_el = self._invoice(self.company_el, 10, days_ago=2)
        inv_he = self._invoice(self.company_he, 5, days_ago=1)
        self.royalty._book_royalties_from_invoices(inv_el + inv_he)
        groups = self.env["account.analytic.line"].sudo()._read_group(
            [("account_id", "=", self.account.id),
             ("edlab_source_move_line_id", "!=", False)],
            groupby=["edlab_source_company_id"],
            aggregates=["amount:sum"],
        )
        totals = {company: amount for company, amount in groups}
        self.assertEqual(set(totals), {self.company_el, self.company_he})
        # 7% sobre 10 x 10,00 (EL) e sobre 5 x 10,00 (HE)
        self.assertAlmostEqual(totals[self.company_el], -7.0, places=2)
        self.assertAlmostEqual(totals[self.company_he], -3.5, places=2)

    def test_pair_accumulates_in_draft(self):
        self._invoice(self.company_el, 80, days_ago=2)
        inv = self.env["account.move"].sudo().search([
            ("company_id", "=", self.company_el.id),
            ("move_type", "=", "out_invoice")])
        self.royalty._book_royalties_from_invoices(inv)
        pair = self._pair_invoices()
        self.assertEqual(len(pair), 1)
        self.assertEqual(pair.state, "draft")
        self.assertEqual(pair.partner_id, self.company_el.partner_id)
        self.assertTrue(pair.ref.startswith("Royalties entre Empresas/"))
        line = pair.invoice_line_ids
        self.assertEqual(len(line), 1)
        # 80 x 10,00 = 800,00 @ 7% -> 56,00 charged
        self.assertAlmostEqual(line.price_unit, 56.0, places=2)
        self.assertEqual(line.edlab_interco_royalty_line_id, self.royalty)
        accrual = self._accruals()
        self.assertEqual(accrual.edlab_interco_move_line_id, line)

    def test_second_sale_grows_same_line(self):
        inv1 = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv1)
        inv2 = self._invoice(self.company_el, 40, days_ago=1)
        self.royalty._book_royalties_from_invoices(inv1 + inv2)
        pair = self._pair_invoices()
        self.assertEqual(len(pair), 1, "same accumulator, not a second pair")
        self.assertEqual(len(pair.invoice_line_ids), 1,
                         "same royalty line = same invoice line, recomputed")
        # 56,00 (80 @ 7%) + 32,00 (40 more crossing into 8%) = 88,00
        self.assertAlmostEqual(pair.invoice_line_ids.price_unit, 88.0, places=2)
        # Re-running with nothing new must change nothing.
        self.royalty._book_royalties_from_invoices(inv1 + inv2)
        pair = self._pair_invoices()
        self.assertEqual(len(pair), 1)
        self.assertEqual(len(pair.invoice_line_ids), 1)
        self.assertAlmostEqual(pair.invoice_line_ids.price_unit, 88.0, places=2)

    def test_post_creates_mirror_bill(self):
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        pair = self._pair_invoices()
        pair.action_post()
        bill = pair.edlab_interco_mirror_of_ids
        self.assertEqual(len(bill), 1)
        self.assertEqual(bill.move_type, "in_invoice")
        self.assertEqual(bill.company_id, self.company_el)
        self.assertEqual(bill.partner_id, self.company_he.partner_id)
        self.assertEqual(bill.state, "draft")
        self.assertEqual(bill.ref, pair.name)
        self.assertTrue(bill.edlab_is_interco_bill)
        self.assertAlmostEqual(
            bill.invoice_line_ids.price_unit, 56.0, places=2)
        self.assertEqual(
            bill.invoice_line_ids.edlab_interco_royalty_line_id, self.royalty)

    def test_new_pair_after_post(self):
        inv1 = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv1)
        posted = self._pair_invoices()
        posted.action_post()
        inv2 = self._invoice(self.company_el, 40, days_ago=1)
        self.royalty._book_royalties_from_invoices(inv1 + inv2)
        drafts = self._pair_invoices(state="draft")
        self.assertEqual(len(drafts), 1, "a new accumulator opens after post")
        self.assertNotEqual(drafts, posted)
        # Only the NEW accrual: 40 copies at 8% (cumulative crossed 100).
        self.assertAlmostEqual(
            drafts.invoice_line_ids.price_unit, 32.0, places=2)
        # The posted pair is settled history and must not move.
        self.assertAlmostEqual(
            posted.invoice_line_ids.filtered(
                "edlab_interco_royalty_line_id").price_unit, 56.0, places=2)

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------
    def test_own_sales_never_charged(self):
        inv = self._invoice(self.company_he, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        self.assertEqual(len(self._accruals()), 1, "own sale still accrues")
        self.assertFalse(self._pair_invoices(),
                         "a company never invoices itself")

    def _account(self, company, code, name, account_type):
        return self.env["account.account"].with_company(company).create({
            "name": name, "code": code, "account_type": account_type,
        })

    def test_income_account_comes_from_the_product(self):
        """No account configured: the charge lands on the product's own
        income account, like any other invoice line."""
        self.company_he.contract_interco_income_account_id = False
        template = self.company_he._contract_interco_product().product_tmpl_id
        income = self._account(
            self.company_he, "999101", "Royalties entre Empresas", "income")
        template.with_company(
            self.company_he).property_account_income_id = income
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        self.assertEqual(
            self._pair_invoices().invoice_line_ids.account_id, income)

    def test_mirror_expense_account_is_the_sellers_own(self):
        """The product's accounts are company-dependent: the mirror bill must
        take the SELLING company's expense account, never the contract
        company's."""
        self.company_el.contract_interco_expense_account_id = False
        template = self.company_he._contract_interco_product().product_tmpl_id
        expense_he = self._account(
            self.company_he, "999201", "Despesa HE", "expense")
        expense_el = self._account(
            self.company_el, "999202", "Despesa EL", "expense")
        template.with_company(
            self.company_he).property_account_expense_id = expense_he
        template.with_company(
            self.company_el).property_account_expense_id = expense_el
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        pair = self._pair_invoices()
        pair.action_post()
        bill = pair.edlab_interco_mirror_of_ids
        self.assertEqual(bill.invoice_line_ids.account_id, expense_el)

    def test_configured_account_overrides_the_product(self):
        """The setting is the override, not the only way in: when both are
        set, the configured account wins."""
        template = self.company_he._contract_interco_product().product_tmpl_id
        from_product = self._account(
            self.company_he, "999301", "Do produto", "income")
        configured = self._account(
            self.company_he, "999302", "Da configuração", "income")
        template.with_company(
            self.company_he).property_account_income_id = from_product
        self.company_he.contract_interco_income_account_id = configured
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        self.assertEqual(
            self._pair_invoices().invoice_line_ids.account_id, configured)

    def test_wrong_sale_journal_type_does_not_abort_the_fill(self):
        """A bank journal in the sale-journal setting must not take the whole
        royalty fill down with it (Odoo refuses a sale document there)."""
        bank = self.env["account.journal"].with_company(
            self.company_he).create({
                "name": "Descarte", "type": "bank", "code": "ZZDES"})
        self.company_he.contract_interco_journal_id = bank
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        pair = self._pair_invoices()
        self.assertTrue(pair, "the charge is still created")
        self.assertEqual(pair.journal_id.type, "sale",
                         "the misconfigured journal is ignored")

    def test_wrong_purchase_journal_type_does_not_break_the_mirror(self):
        bank = self.env["account.journal"].with_company(
            self.company_el).create({
                "name": "Refunds", "type": "bank", "code": "ZZREF"})
        self.company_el.contract_interco_purchase_journal_id = bank
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        pair = self._pair_invoices()
        pair.action_post()
        bill = pair.edlab_interco_mirror_of_ids
        self.assertEqual(len(bill), 1, "the mirror is still created")
        self.assertEqual(bill.journal_id.type, "purchase")

    def test_markup(self):
        self.company_he.contract_interco_markup = 10.0
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        # 56,00 + 10% administration = 61,60
        self.assertAlmostEqual(
            self._pair_invoices().invoice_line_ids.price_unit, 61.6, places=2)

    def test_cutoff_and_advance_not_charged(self):
        self.royalty.recoupable_advance = 100.0
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        self.royalty.sudo().last_payment_date = fields.Date.today()
        self.royalty._book_royalties_from_invoices(inv)
        # Advance (+100) and cutoff entries carry no source company, so the
        # charge stays the plain accrued royalty.
        self.assertAlmostEqual(
            self._pair_invoices().invoice_line_ids.price_unit, 56.0, places=2)

    def test_domain_restricts_companies(self):
        domain = self.contract._edlab_royalty_invoice_domain()
        term = [t for t in domain if t[0] == "company_id"]
        self.assertEqual(len(term), 1)
        self.assertCountEqual(
            term[0][2], (self.company_he | self.company_el).ids)
        self.company_he.contract_interco_source_company_ids = [(5, 0, 0)]
        domain = self.contract._edlab_royalty_invoice_domain()
        term = [t for t in domain if t[0] == "company_id"]
        self.assertEqual(term[0][2], self.company_he.ids,
                         "empty config = only the company's own sales")

    def test_cancel_draft_releases_accruals(self):
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        pair = self._pair_invoices()
        pair.button_cancel()
        self.assertFalse(self._accruals().edlab_interco_move_line_id,
                         "cancelling the charge frees its accruals")
        self.royalty._book_royalties_from_invoices(inv)
        rebuilt = self._pair_invoices(state="draft")
        self.assertEqual(len(rebuilt), 1)
        self.assertAlmostEqual(
            rebuilt.invoice_line_ids.price_unit, 56.0, places=2)

    # ------------------------------------------------------------------
    # Error / degraded paths
    # ------------------------------------------------------------------
    def test_missing_product_skips_charge(self):
        # Drop the XML-ID, not the product: in a live database the shipped
        # product is already on real invoice lines, and deleting it would
        # fail on the foreign key instead of testing anything. Losing the
        # xmlid is the same thing as far as the fallback is concerned --
        # env.ref no longer resolves it.
        self.env["ir.model.data"].search([
            ("module", "=", "liber_copyright_contracts_intercompany"),
            ("name", "=", "product_interco_royalty"),
        ]).unlink()
        self.env.registry.clear_cache()
        self.company_he.contract_interco_product_id = False
        inv = self._invoice(self.company_el, 80, days_ago=2)
        # The charge is optional; the accrual must never be blocked by it.
        self.royalty._book_royalties_from_invoices(inv)
        self.assertEqual(len(self._accruals()), 1)
        self.assertFalse(self._pair_invoices())

    def test_user_without_el_access_can_fill(self):
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self._pay(inv)
        self.assertIn(inv.payment_state, ("paid", "in_payment"),
                      "the EL invoice must read as paid for the fill to see it")
        user = self.env["res.users"].create({
            "name": "Gestor HE",
            "login": "gestor_he_interco",
            "company_id": self.company_he.id,
            "company_ids": [(6, 0, self.company_he.ids)],
            "group_ids": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref(
                    "liber_copyright_contracts.group_contract_user").id,
            ])],
        })
        # An HE-only user runs the fill over EL sales: every cross-company
        # read/write is sudo'ed, so no AccessError and the pair is born.
        res = self.contract.with_user(user).action_fill_royalty_lines()
        self.assertEqual(len(self._accruals()), 1,
                         res.get("params", {}).get("message"))
        self.assertAlmostEqual(
            self._pair_invoices().invoice_line_ids.price_unit, 56.0, places=2)

    # ------------------------------------------------------------------
    # Coexistence with account_invoice_inter_company (OCA)
    # ------------------------------------------------------------------
    def _oca_present(self):
        if "auto_invoice_id" not in self.env["account.move"]._fields:
            self.skipTest("account_invoice_inter_company (OCA) not installed")
        for company in self.company_he | self.company_el:
            company.write({"intercompany_invoicing": True,
                           "invoice_auto_validation": False})

    def _oca_mirrors_of(self, move):
        return self.env["account.move"].sudo().search(
            [("auto_invoice_id", "=", move.id)])

    def test_oca_does_not_double_the_royalty_pair(self):
        """With the OCA mirror on, a royalty invoice still yields exactly one
        bill (ours), and posting that bill yields no extra invoice."""
        self._oca_present()
        inv = self._invoice(self.company_el, 80, days_ago=2)
        self.royalty._book_royalties_from_invoices(inv)
        pair = self._pair_invoices()
        pair.action_post()
        self.assertEqual(len(pair.edlab_interco_mirror_of_ids), 1)
        self.assertFalse(self._oca_mirrors_of(pair))
        bill = pair.edlab_interco_mirror_of_ids
        bill.sudo().with_company(self.company_el).action_post()
        self.assertFalse(self._oca_mirrors_of(bill))
        self.assertEqual(self.env["account.move"].sudo().search_count([
            ("company_id", "=", self.company_he.id),
            ("move_type", "=", "out_invoice"),
            ("partner_id", "=", self.company_el.partner_id.id),
        ]), 1)

    def test_oca_still_mirrors_an_ordinary_sister_invoice(self):
        """The guard is narrow: a plain invoice to a sister company keeps
        getting its OCA mirror."""
        self._oca_present()
        move = self.env["account.move"].with_company(self.company_he).create({
            "move_type": "out_invoice",
            "company_id": self.company_he.id,
            "partner_id": self.company_el.partner_id.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [(0, 0, {
                "product_id": self.book.product_variant_id.id,
                "quantity": 1, "price_unit": 10.0})],
        })
        move.action_post()
        mirror = self._oca_mirrors_of(move)
        self.assertEqual(len(mirror), 1)
        self.assertEqual(mirror.company_id, self.company_el)
        self.assertEqual(mirror.move_type, "in_invoice")
