# -*- coding: utf-8 -*-
"""Licensing: the invoice the contract makes, and the author's share it books."""
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from .common import LicensingCommon


@tagged("post_install", "-at_install", "copyright_licensing")
class TestLicensing(LicensingCommon, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_licensing()

    # ------------------------------------------------------------------
    # The invoice the contract makes
    # ------------------------------------------------------------------
    def test_new_invoice_comes_ready(self):
        """New from the contract: contract's company, licensing product, the
        configured income account and the author's analytic at 100%."""
        move = self._new_licence(post=False)
        self.assertEqual(move.edlab_license_contract_id, self.contract)
        self.assertEqual(move.move_type, "out_invoice")
        self.assertEqual(move.company_id, self.contract.company_id)
        self.assertEqual(move.journal_id.type, "sale")
        line = move.invoice_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_id, self.company._contract_license_product())
        self.assertEqual(
            line.product_id.product_tmpl_id,
            self.env.ref("liber_copyright_contracts_licensing.product_rights_licensing"))
        self.assertEqual(line.account_id, self.income)
        self.assertEqual(line.analytic_distribution, {str(self.account.id): 100.0})
        self.assertEqual(self.contract.edlab_license_count, 1)

    def test_line_says_which_work_was_licensed(self):
        """Core would name the line after the generic product ("Rights
        licensing"); the licensee has to read the book's title."""
        move = self._new_licence(post=False)
        name = move.invoice_line_ids.name
        self.assertIn(self.book.name, name)
        self.assertIn(self.contract.name, name)

    def test_typed_description_is_kept(self):
        move = self._new_licence(post=False)
        move.invoice_line_ids.name = "Poema A Triste Partida, antologia escolar"
        move.invoice_line_ids.price_unit = 2000.0
        self.assertEqual(move.invoice_line_ids.name,
                         "Poema A Triste Partida, antologia escolar")

    def test_settings_show_the_product_from_the_start(self):
        """Settings must not read "not configured": the install fills every
        company, and a company created later starts filled."""
        from odoo.addons.liber_copyright_contracts_licensing import post_init_hook
        default = self.env.ref(
            "liber_copyright_contracts_licensing.product_rights_licensing"
        ).product_variant_id
        self.company.contract_license_product_id = False
        post_init_hook(self.env)
        self.assertEqual(self.company.contract_license_product_id, default)
        other = self.env["res.company"].create({"name": "Editora Nova"})
        self.assertEqual(other.contract_license_product_id, default)

    def test_configured_product_and_journal_win(self):
        product = self.env["product.product"].create({
            "name": "Cessão de direitos", "type": "service"})
        journal = self.env["account.journal"].create({
            "name": "Licenças", "code": "LICJ", "type": "sale",
            "company_id": self.company.id})
        self.company.write({
            "contract_license_product_id": product.id,
            "contract_license_journal_id": journal.id,
        })
        move = self._new_licence(post=False)
        self.assertEqual(move.journal_id, journal)
        self.assertEqual(move.invoice_line_ids.product_id, product)

    def test_smart_button_action_lists_only_this_contract(self):
        move = self._new_licence(post=False)
        other = self._sell(1)
        action = self.contract.action_view_license_invoices()
        found = self.env["account.move"].search(action["domain"])
        self.assertEqual(found, move)
        self.assertNotIn(other, found)
        self.assertEqual(
            action["context"]["default_edlab_license_contract_id"], self.contract.id)
        self.assertNotIn("default_journal_id", action["context"],
                         "a journal default in the action would leak into "
                         "the payment wizard opened from the invoice")

    # ------------------------------------------------------------------
    # The author's share
    # ------------------------------------------------------------------
    def test_share_accrues_only_when_paid(self):
        move = self._new_licence(amount=1000.0, pay=False)
        self.assertFalse(self._licence_entries(), "posted is not paid")
        self._pay(move)
        entry = self._licence_entries()
        self.assertEqual(len(entry), 1)
        self.assertAlmostEqual(entry.amount, -400.0, places=2)
        self.assertEqual(entry.account_id, self.account)
        self.assertAlmostEqual(entry.edlab_royalty_percentage, 40.0)
        self.assertEqual(entry.edlab_source_move_line_id, move.invoice_line_ids)
        self.assertAlmostEqual(self.royalty._edlab_open_balance(), 400.0, places=2)

    def test_core_full_amount_is_not_booked_on_author_account(self):
        """The +100% core entry would make the author 'owe' the house."""
        move = self._new_licence(amount=1000.0)
        core = self.env["account.analytic.line"].sudo().search(
            [("move_line_id", "in", move.line_ids.ids)])
        self.assertFalse(core)
        plan_column = self.account.plan_id._column_name()
        balance = sum(self.env["account.analytic.line"].sudo().search(
            [(plan_column, "=", self.account.id)]).mapped("amount"))
        self.assertAlmostEqual(balance, -400.0, places=2)

    def test_other_plans_on_the_line_keep_their_entry(self):
        plan = self.env["account.analytic.plan"].create({"name": "Projetos teste"})
        project = self.env["account.analytic.account"].create({
            "name": "Antologia escolar", "plan_id": plan.id,
            "company_id": self.company.id})
        move = self._new_licence(amount=1000.0, post=False)
        move.invoice_line_ids.analytic_distribution = {
            str(self.account.id): 100.0, str(project.id): 100.0}
        move.action_post()
        core = self.env["account.analytic.line"].sudo().search(
            [("move_line_id", "in", move.line_ids.ids)])
        self.assertEqual(len(core), 1)
        self.assertEqual(core[plan._column_name()], project)
        self.assertAlmostEqual(core.amount, 1000.0, places=2)

    def test_fill_is_idempotent(self):
        self._new_licence(amount=1000.0)
        self.contract.action_fill_royalty_lines()
        self.contract.action_fill_royalty_lines()
        self.assertEqual(len(self._licence_entries()), 1)

    def test_fill_books_a_licence_reset_away(self):
        """Reset Analytics wipes generated entries; Fill rebuilds the licence."""
        self._new_licence(amount=500.0)
        self.contract.action_reset_analytics()
        self.assertFalse(self._licence_entries())
        res = self.contract.action_fill_royalty_lines()
        self.assertEqual(len(self._licence_entries()), 1)
        # The count, not the wording: the message is translated (pt_BR on
        # the house databases).
        self.assertIn("1", res["params"]["message"].split(".")[0])
        self.assertEqual(res["params"]["type"], "success")

    def test_licence_billed_with_the_work_product_does_not_accrue_twice(self):
        move = self._new_licence(amount=1000.0, post=False)
        move.invoice_line_ids.product_id = self.book.product_variant_id
        move.invoice_line_ids.price_unit = 1000.0
        move.action_post()
        self._pay(move)
        self.contract.action_fill_royalty_lines()
        entries = self.env["account.analytic.line"].sudo().search(
            [("account_id", "=", self.account.id),
             ("edlab_source_move_line_id", "!=", False)])
        self.assertEqual(len(entries), 1, "only the licensing share, no tier accrual")
        self.assertAlmostEqual(entries.amount, -400.0, places=2)

    def test_zero_percentage_accrues_nothing(self):
        self.royalty.license_percentage = 0.0
        self._new_licence(amount=1000.0)
        self.contract.action_fill_royalty_lines()
        self.assertFalse(self._licence_entries())

    def test_percentage_must_be_a_percentage(self):
        with self.assertRaises(ValidationError):
            self.royalty.license_percentage = 140.0
        with self.assertRaises(ValidationError):
            self.royalty.license_percentage = -5.0

    def test_licence_outside_the_contract_term_accrues_nothing(self):
        before = self.contract.signature_date - timedelta(days=10)
        self._new_licence(amount=1000.0, invoice_date=before)
        self.assertFalse(self._licence_entries())

    def test_unpaid_again_removes_the_unsettled_share(self):
        move = self._new_licence(amount=1000.0)
        self.assertTrue(self._licence_entries())
        move.line_ids.remove_move_reconcile()
        self.assertEqual(move.payment_state, "not_paid")
        self.assertFalse(self._licence_entries())

    def test_share_already_paid_to_the_author_is_history(self):
        move = self._new_licence(amount=1000.0)
        self.royalty.sudo().last_payment_date = fields.Date.today()
        move.line_ids.remove_move_reconcile()
        self.assertEqual(len(self._licence_entries()), 1,
                         "an entry the author was already paid is not erased")

    def test_two_beneficiaries_each_take_their_share_of_the_whole(self):
        heir = self.env["res.partner"].create({"name": "Herdeira"})
        self.contract.write({"royalty_line_ids": [Command.create({
            "partner_id": heir.id, "product_id": self.book.id,
            "license_percentage": 20.0})]})
        heir_line = self.contract.royalty_line_ids - self.royalty
        heir_line.action_create_analytic_account()
        move = self._new_licence(amount=1000.0)
        self.assertEqual(len(move.invoice_line_ids), 1, "one line per work")
        self.assertAlmostEqual(self.royalty._edlab_open_balance(), 400.0, places=2)
        self.assertAlmostEqual(heir_line._edlab_open_balance(), 200.0, places=2)

    def test_invoice_must_be_in_the_contract_company(self):
        other = self.env["res.company"].create({"name": "Outra Editora"})
        contract = self.env["edlab.contract"].create({"company_id": other.id})
        with self.assertRaises(ValidationError):
            self.env["account.move"].create({
                "move_type": "out_invoice",
                "partner_id": self.licensee.id,
                "edlab_license_contract_id": contract.id,
            })

    # ------------------------------------------------------------------
    # Downstream: bill, statement
    # ------------------------------------------------------------------
    def test_author_bill_pays_the_licence(self):
        self._new_licence(amount=1000.0)
        self.contract.action_generate_royalty_bills()
        bill = self.contract.edlab_bill_ids
        self.assertEqual(len(bill), 1)
        self.assertAlmostEqual(bill.amount_untaxed, 400.0, places=2)

    def test_statement_lists_licences_apart(self):
        self._sell(10)                       # 100,00 @ 10% -> 10,00
        self.contract.action_fill_royalty_lines()
        self._new_licence(amount=1000.0)     # 1.000,00 @ 40% -> 400,00
        st = self.author._edlab_royalty_statement()
        self.assertAlmostEqual(st["accrued"], 410.0, places=2)
        self.assertAlmostEqual(st["total"], self.royalty._edlab_open_balance(), places=2)
        self.assertEqual(len(st["rows"]), 1)
        row = st["rows"][0]
        self.assertEqual(row["qty"], 10)
        self.assertAlmostEqual(row["base"], 100.0, places=2)
        self.assertEqual(row["percentage_label"], "10,00%")
        self.assertAlmostEqual(row["amount"], 10.0, places=2)
        self.assertEqual(len(st["licensing"]), 1)
        lic = st["licensing"][0]
        self.assertEqual(lic["licensee"], "Editora Didática")
        self.assertAlmostEqual(lic["base"], 1000.0, places=2)
        self.assertEqual(lic["percentage_label"], "40,00%")
        self.assertAlmostEqual(lic["amount"], 400.0, places=2)
        self.assertAlmostEqual(st["licensing_total"], 400.0, places=2)
        self.assertAlmostEqual(st["royalties_total"], 10.0, places=2)

    def test_statement_with_only_a_licence(self):
        self._new_licence(amount=250.0)
        st = self.author._edlab_royalty_statement()
        self.assertEqual(st["rows"], [])
        self.assertAlmostEqual(st["licensing_total"], 100.0, places=2)
        self.assertAlmostEqual(st["accrued"], 100.0, places=2)

    def test_statement_pdf_renders_the_section(self):
        self._new_licence(amount=1000.0)
        report = self.env.ref(
            "liber_copyright_contracts_reports.action_report_royalty_statement")
        html, _kind = self.env["ir.actions.report"]._render_qweb_html(
            report, self.author.ids)
        html = html.decode()
        self.assertIn("licensing", html)
        self.assertIn("Editora Didática", html)

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    def test_contract_user_reads_the_licences_and_nothing_else(self):
        user = self.env["res.users"].create({
            "name": "Assistente", "login": "assist_licensing",
            "group_ids": [
                Command.link(self.env.ref("base.group_user").id),
                Command.link(self.env.ref(
                    "liber_copyright_contracts.group_contract_user").id)],
        })
        licence = self._new_licence(amount=1000.0)
        sale = self._sell(1)
        Move = self.env["account.move"].with_user(user)
        visible = Move.search([("id", "in", (licence | sale).ids)])
        self.assertEqual(visible, licence)
        action = self.contract.with_user(user).action_view_license_invoices()
        self.assertEqual(Move.search(action["domain"]), licence)
