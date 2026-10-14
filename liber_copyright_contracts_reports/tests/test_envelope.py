# -*- coding: utf-8 -*-
"""Stage 2 of the mailed statement: the beneficiary block at the top, the
address block where the envelope window falls, the proof print, and the
letterhead that must stay above the window."""
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .test_reports import TestRoyaltyStatement


@tagged("post_install", "-at_install", "copyright_reports")
class TestEnvelopeStatement(TestRoyaltyStatement):
    allow_inherited_tests_method = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.author.write({
            "street": "Rua das Laranjeiras, 10", "zip": "22240-000",
            "city": "Rio de Janeiro", "vat": "123.456.789-09",
            "edlab_birthdate": "1881-05-13", "edlab_birth_place": "Rio de Janeiro, RJ",
            "edlab_marital_status": "single", "edlab_race": "black",
            "email": "lima@example.org",
        })
        bank = cls.env["res.bank"].create({"name": "Banco do Brasil"})
        cls.env["res.partner.bank"].create({
            "partner_id": cls.author.id, "bank_id": bank.id,
            "acc_number": "12345-6", "edlab_agency": "0001",
            "edlab_pix_key_type": "email", "edlab_pix_key": "lima@example.org",
            "edlab_prefer_pix": True})

    def test_window_in_body_coordinates_and_fold_lines(self):
        self.company.write({"edlab_envelope_window_top": 45, "edlab_envelope_window_left": 20,
                            "edlab_envelope_window_width": 95, "edlab_envelope_window_height": 40,
                            "edlab_statement_header_height": 30})
        window = self.company._edlab_envelope_window()
        self.assertEqual(window["top"], 15.0)
        self.assertEqual(window["left"], 20.0)
        self.assertEqual(window["folds"], [69.0, 168.0])
        paperformat = self.env.ref("liber_copyright_contracts_reports.paperformat_royalty_statement")
        self.assertEqual(paperformat.margin_top, 30.0)
        self.company.edlab_statement_header_height = 25
        self.assertEqual(paperformat.margin_top, 25.0)
        self.assertEqual(paperformat.header_spacing, 23.0)
        self.assertEqual(self.company._edlab_envelope_window()["top"], 20.0)

    def test_letterhead_over_the_window_is_refused(self):
        self.company.write({"edlab_envelope_window_top": 30,
                            "edlab_statement_header_height": 40})
        with self.assertRaises(UserError):
            self.company._edlab_envelope_window()
        with self.assertRaises(UserError):
            self.company.write({"edlab_envelope_window_top": 70,
                                "edlab_envelope_window_height": 40})

    def test_header_rows_person(self):
        hdr = self.author._edlab_statement_header()
        self.assertEqual(hdr["address_lines"],
                         ["Lima Barreto", "Rua das Laranjeiras, 10",
                          "22240-000 Rio de Janeiro"])
        rows = dict(hdr["identification"])
        self.assertEqual(rows["CPF"], "123.456.789-09")
        self.assertEqual(rows["Birth"], "13/05/1881 (Rio de Janeiro, RJ)")
        self.assertEqual(rows["Marital status"], "Single")
        self.assertEqual(rows["Race/color"], "Black (preta)")
        self.assertNotIn("Education", rows)
        pay = hdr["payment"]
        self.assertEqual(pay[0], ("Pix", "E-mail lima@example.org"))
        self.assertEqual(dict(pay)["Bank"], "Banco do Brasil")
        self.assertEqual(dict(pay)["Checking"], "12345-6")
        self.assertNotIn("Currency", dict(pay))

    def test_header_rows_company(self):
        rep = self.env["res.partner"].create({"name": "Maria Gerente"})
        firm = self.env["res.partner"].create({
            "name": "Editora Parceira Ltda", "is_company": True, "vat": "12.345.678/0001-90",
            "edlab_municipal_registration": "987", "edlab_legal_representative_id": rep.id,
            "street": "Av. Paulista, 1000", "city": "São Paulo"})
        rows = dict(firm._edlab_statement_header()["identification"])
        self.assertEqual(rows["Legal name"], "Editora Parceira Ltda")
        self.assertEqual(rows["CNPJ"], "12.345.678/0001-90")
        self.assertEqual(rows["Collaborator"], "Maria Gerente")
        self.assertIn("Av. Paulista, 1000", rows["Head office"])
        self.assertNotIn("CPF", rows)

    def test_statement_prints_sensitive_rows_for_a_plain_user(self):
        user = new_test_user(
            self.env, login="statement_printer",
            groups="base.group_user,liber_copyright_contracts.group_contract_user,"
                   "account.group_account_invoice")
        hdr = self.author.with_user(user)._edlab_statement_header()
        self.assertEqual(dict(hdr["identification"])["Race/color"], "Black (preta)")

    def test_html_has_the_window_block_before_the_summary(self):
        self.company.write({"edlab_envelope_window_top": 45, "edlab_envelope_window_left": 20,
                            "edlab_envelope_window_width": 95, "edlab_envelope_window_height": 40,
                            "edlab_statement_header_height": 30})
        self._sell_and_book(10)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "liber_copyright_contracts_reports.report_royalty_statement",
            self.author.ids)[0].decode()
        window = html.index("edlab-window")
        self.assertIn("top: 15.0mm; left: 20.0mm; width: 95.0mm; height: 40.0mm", html)
        self.assertLess(window, html.index("beneficiary"))
        self.assertLess(html.index("beneficiary"), html.index("summary"))
        self.assertIn("Pix</strong> <span>E-mail lima@example.org", html.replace("\n", ""))
        self.assertNotIn("Dados bancários", html)

    def test_proof_renders_frame_and_folds(self):
        html = self.env["ir.actions.report"]._render_qweb_html(
            "liber_copyright_contracts_reports.report_envelope_proof",
            self.author.ids)[0].decode()
        self.assertIn("border: 1px dashed", html)
        self.assertEqual(html.count(">fold<"), 2)
        self.assertIn("Envelope proof: window 57.0 mm from the top", html)
        self.assertIn("Lima Barreto", html)

    def test_pdf_really_renders_with_the_statement_paperformat(self):
        action = self.env.ref("liber_copyright_contracts_reports.action_report_royalty_statement")
        self.assertEqual(action.paperformat_id.margin_top, 52.0)
        pdf, kind = action.with_context(force_report_rendering=True)._render_qweb_pdf(
            "liber_copyright_contracts_reports.report_royalty_statement", self.author.ids)
        self.assertEqual(kind, "pdf")
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_email_version_drops_the_window_but_keeps_the_person(self):
        self._sell_and_book(10)
        report = self.env["ir.actions.report"]
        printed = report._render_qweb_html(
            "liber_copyright_contracts_reports.report_royalty_statement",
            self.author.ids)[0].decode()
        mailed = report._render_qweb_html(
            "liber_copyright_contracts_reports.report_royalty_statement",
            self.author.ids, data={"no_window": True})[0].decode()
        self.assertIn("edlab-window", printed)
        self.assertNotIn("edlab-window", mailed)
        for html in (printed, mailed):
            self.assertIn("Race/color", html)
            self.assertIn("Rua das Laranjeiras", html)
        statement, pdf = self.author._edlab_statement_pdf(for_email=True)
        self.assertTrue(pdf.startswith(b"%PDF"))
