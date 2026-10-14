# -*- coding: utf-8 -*-
"""A legal-entity beneficiary: trade name, CNPJ, municipal registration and
the collaborator who handles the contract. None of it is sensitive, so a
plain contracts user reads it all and sees the fields on the form."""
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "copyright_reports")
class TestBeneficiaryCompany(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.collaborator = cls.env["res.partner"].create({
            "name": "Ana Editora", "is_company": False})
        cls.company_partner = cls.env["res.partner"].create({
            "name": "Agência Literária Ltda.",
            "is_company": True,
            "vat": "12.345.678/0001-90",
            "edlab_trade_name": "Agência Literária",
            "edlab_municipal_registration": "1.234.567-8",
            "edlab_legal_representative_id": cls.collaborator.id,
        })

    def test_fields_hold_the_data(self):
        partner = self.company_partner
        self.assertTrue(partner.is_company)
        self.assertEqual(partner.edlab_trade_name, "Agência Literária")
        self.assertEqual(partner.vat, "12.345.678/0001-90")
        self.assertEqual(partner.edlab_municipal_registration, "1.234.567-8")
        self.assertEqual(partner.edlab_legal_representative_id, self.collaborator)
        self.assertFalse(self.collaborator.is_company)

    def test_contracts_user_reads_and_sees_the_fields(self):
        user = new_test_user(
            self.env, login="contracts_user_company",
            groups="base.group_user,liber_copyright_contracts.group_contract_user")
        self.env.invalidate_all()
        partner = self.company_partner.with_user(user)
        self.assertEqual(partner.edlab_trade_name, "Agência Literária")
        self.assertEqual(partner.edlab_legal_representative_id, self.collaborator)
        self.assertEqual(partner.edlab_municipal_registration, "1.234.567-8")
        arch = self.env["res.partner"].with_user(user).get_views(
            [(False, "form")])["views"]["form"]["arch"]
        self.assertIn("edlab_trade_name", arch)
        self.assertIn("edlab_legal_representative_id", arch)
