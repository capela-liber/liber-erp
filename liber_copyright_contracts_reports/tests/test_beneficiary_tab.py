# -*- coding: utf-8 -*-
"""The beneficiary's data: the new fields hold what the post needs, the Pix
key is checked before it reaches a statement, and the sensitive block
(marital status, education, race) reads only for the contracts manager."""
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

LOGIN = "beneficiary_tab_tour"


@tagged("post_install", "-at_install", "copyright_reports")
class TestBeneficiaryData(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = cls.env["res.partner"].create({
            "name": "Lima Barreto", "vat": "123.456.789-09",
            "edlab_marital_status": "single", "edlab_education": "higher",
            "edlab_race": "black", "edlab_birth_place": "Rio de Janeiro, RJ",
        })
        cls.bank = cls.env["res.bank"].create({"name": "Banco do Tour"})

    def _account(self, **vals):
        return self.env["res.partner.bank"].create(dict(
            {"partner_id": self.author.id, "bank_id": self.bank.id,
             "acc_number": "12345-6", "edlab_agency": "0001"}, **vals))

    def test_fields_hold_the_data(self):
        self.assertEqual(self.author.edlab_race, "black")
        self.assertEqual(self.author.edlab_beneficiary_currency_id,
                         self.env.company.currency_id)
        account = self._account(edlab_pix_key_type="email",
                                edlab_pix_key="lima@example.org",
                                edlab_prefer_pix=True)
        self.assertEqual(account.edlab_account_kind, "checking")
        self.assertEqual(account._edlab_pix_label(), "E-mail lima@example.org")
        self.assertEqual(self._account(acc_number="7")._edlab_pix_label(), "")

    def test_pix_key_and_type_go_together(self):
        with self.assertRaises(ValidationError):
            self._account(edlab_pix_key="lima@example.org")
        with self.assertRaises(ValidationError):
            self._account(edlab_pix_key_type="email")
        with self.assertRaises(ValidationError):
            self._account(edlab_prefer_pix=True)

    def test_pix_key_shape_follows_its_type(self):
        with self.assertRaises(ValidationError):
            self._account(edlab_pix_key_type="email", edlab_pix_key="lima")
        with self.assertRaises(ValidationError):
            self._account(edlab_pix_key_type="cpf", edlab_pix_key="123")
        self._account(edlab_pix_key_type="cpf", edlab_pix_key="123.456.789-09")
        with self.assertRaises(ValidationError):
            self._account(acc_number="1", edlab_pix_key_type="phone",
                          edlab_pix_key="11 9999")
        self._account(acc_number="2", edlab_pix_key_type="phone",
                      edlab_pix_key="+55 11 99999-9999")
        self._account(acc_number="3", edlab_pix_key_type="random",
                      edlab_pix_key="b1c2d3e4-f5a6-7890")

    def test_sensitive_block_reads_only_for_the_manager(self):
        user = new_test_user(
            self.env, login="contracts_user_tab",
            groups="base.group_user,liber_copyright_contracts.group_contract_user")
        manager = new_test_user(
            self.env, login="contracts_manager_tab",
            groups="base.group_user,liber_copyright_contracts.group_contract_manager")
        self.env.invalidate_all()
        self.assertEqual(self.author.with_user(manager).edlab_race, "black")
        self.assertEqual(self.author.with_user(user).edlab_birth_place,
                         "Rio de Janeiro, RJ")
        with self.assertRaises(AccessError):
            self.author.with_user(user).read(["edlab_race"])
        with self.assertRaises(AccessError):
            self.author.with_user(user).read(["edlab_marital_status"])
        # And the form the user gets simply has no such field.
        arch = self.env["res.partner"].with_user(user).get_views(
            [(False, "form")])["views"]["form"]["arch"]
        self.assertNotIn("edlab_race", arch)
        self.assertIn("edlab_birthdate", arch)


@tagged("post_install", "-at_install", "copyright_reports_tour")
class TestBeneficiaryTabTour(HttpCase):
    def test_beneficiary_tab_tour(self):
        company = self.env.company
        self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Contracts Manager (tab tour)",
            "login": LOGIN,
            "password": LOGIN,
            "lang": "en_US",
            "company_id": company.id,
            "company_ids": [(6, 0, [company.id])],
            "group_ids": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("liber_copyright_contracts.group_contract_manager").id])],
        })
        author = self.env["res.partner"].create({
            "name": "Autor do Tour", "edlab_race": "not_declared",
            "edlab_birthdate": "1980-05-01", "lang": "en_US"})
        bank = self.env["res.bank"].create({"name": "Banco do Tour"})
        self.env["res.partner.bank"].create({
            "partner_id": author.id, "bank_id": bank.id, "acc_number": "9-9",
            "edlab_pix_key_type": "email", "edlab_pix_key": "autor@example.org"})
        book = self.env["product.template"].create({
            "name": "Livro do Tour", "type": "consu", "list_price": 10.0})
        self.env["edlab.contract"].create({
            "signature_date": "2026-01-01", "expiration_date": "2028-01-01",
            "royalty_line_ids": [(0, 0, {"partner_id": author.id,
                                         "product_id": book.id})],
        })
        self.start_tour(f"/odoo/contacts/{author.id}", "beneficiary_tab_tour",
                        login=LOGIN)
