# -*- coding: utf-8 -*-
"""What the document says about the record holding it.

Two rules, both about the same thing: a CNPJ belongs to a legal entity, and a
register that reads it as a person is wrong. In the 2026 merge 26 contacts held
a CNPJ while ticked 'Individual' -- LIVRARIA DA CENTRAL, Paulinas, Novo Século.

The rule runs in one direction only, and that is the part worth guarding with a
test: 36 real companies in the same base carry a CPF in ``vat``, including Edlab
Press and n-1. There the document is wrong, not the record. A symmetric rule
would turn both publishers into natural persons.

The formatting is the small half: it does not decide anything, it only makes a
column of documents readable. It stays away from what it cannot read -- foreign
vats, and the ten documents in this base with 5, 8, 12, 13 or 15 digits.
"""
from odoo.tests import TransactionCase, tagged

CNPJ_DIGITS = "11222333000181"
CNPJ_PRETTY = "11.222.333/0001-81"
OTHER_CNPJ = "43828151000226"
CPF_DIGITS = "12345678909"
CPF_PRETTY = "123.456.789-09"
# O dígito verificador não fecha: 04354383000106 é o CNPJ que estava nas
# constantes deste arquivo, e descobriu-se inválido ao escrever o validador.
CNPJ_BROKEN = "04.354.383/0001-06"


@tagged("post_install", "-at_install")
class TestPartnerDocumentRules(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]

    # --- a máscara -------------------------------------------------------

    def test_cnpj_is_punctuated_on_create(self):
        partner = self.Partner.create({"name": "Livraria X", "vat": CNPJ_DIGITS})
        self.assertEqual(partner.vat, CNPJ_PRETTY)

    def test_cpf_is_punctuated_on_create(self):
        partner = self.Partner.create({"name": "Leitor X", "vat": CPF_DIGITS})
        self.assertEqual(partner.vat, CPF_PRETTY)

    def test_document_is_punctuated_on_write(self):
        partner = self.Partner.create({"name": "Livraria Y"})
        partner.vat = CNPJ_DIGITS
        self.assertEqual(partner.vat, CNPJ_PRETTY)

    def test_digits_stay_in_step_with_the_mask(self):
        """Formatting must not cost the field the import matches on."""
        partner = self.Partner.create({"name": "Livraria Z", "vat": CNPJ_DIGITS})
        self.assertEqual(partner.vat_digits, CNPJ_DIGITS)

    def test_foreign_vat_is_left_alone(self):
        """'FR12345678901' reduces to eleven digits and is not a CPF."""
        partner = self.Partner.create({"name": "Éditions Y", "vat": "FR12345678901"})
        self.assertEqual(partner.vat, "FR12345678901")

    def test_broken_document_is_left_as_typed(self):
        """Twelve digits is neither: inventing separators would hide the defect."""
        partner = self.Partner.create({"name": "Comix", "vat": "346986000156"})
        self.assertEqual(partner.vat, "346986000156")

    # --- CNPJ manda ser empresa ------------------------------------------

    def test_cnpj_makes_a_company_on_create(self):
        partner = self.Partner.create({"name": "LIVRARIA DA CENTRAL", "vat": CNPJ_PRETTY})
        self.assertTrue(partner.is_company)

    def test_cnpj_makes_a_company_on_write(self):
        partner = self.Partner.create({"name": "Papelaria Madre Neuza"})
        self.assertFalse(partner.is_company)
        partner.vat = CNPJ_PRETTY
        self.assertTrue(partner.is_company)

    def test_cpf_does_not_demote_a_company(self):
        """The n-1 case: a real publisher whose vat holds someone's CPF."""
        empresa = self.Partner.create({"name": "n-1 Edições", "is_company": True})
        empresa.vat = CPF_PRETTY
        self.assertTrue(empresa.is_company, "the document is wrong, not the record")

    def test_cpf_leaves_a_person_alone(self):
        partner = self.Partner.create({"name": "Leitora", "vat": CPF_PRETTY})
        self.assertFalse(partner.is_company)

    def test_cpf_unticks_company_on_a_new_record(self):
        """The Contacts app hands every new contact `default_is_company=True`.

        Without this, typing a CPF into 'Novo' leaves a person filed as a
        company -- and a spreadsheet of readers imports as a spreadsheet of
        companies.
        """
        partner = self.Partner.with_context(default_is_company=True).create(
            {"name": "TESTE", "vat": CPF_PRETTY})
        self.assertFalse(partner.is_company)

    def test_cpf_does_not_demote_a_saved_company(self):
        """The n-1 case again, now from the form: 37 saved companies hold a CPF."""
        empresa = self.Partner.create({"name": "n-1 Edições", "is_company": True})
        empresa.vat = CPF_PRETTY  # write: never demotes
        self.assertTrue(empresa.is_company)

        form = self.Partner.browse(empresa.id)
        form.vat = CPF_DIGITS
        form._onchange_vat_document_br()  # onchange on a SAVED record
        self.assertTrue(form.is_company, "reopening the form must not demote it")

    def test_a_company_with_contacts_is_no_natural_person(self):
        """Even brand new: whatever the document says, people have no contacts."""
        empresa = self.Partner.create({"name": "Casa", "is_company": True})
        self.Partner.create({"name": "Funcionário", "parent_id": empresa.id})
        nova = self.Partner.create({
            "name": "Outra Casa", "is_company": True,
            "child_ids": [(0, 0, {"name": "Contato"})], "vat": CPF_PRETTY})
        self.assertTrue(nova.is_company)

    def test_child_holding_the_parent_document_stays_a_person(self):
        """Alexandre carries the Panaceia's CNPJ; he is not a company."""
        mae = self.Partner.create({"name": "Panaceia", "is_company": True, "vat": CNPJ_PRETTY})
        filho = self.Partner.create({"name": "Alexandre", "parent_id": mae.id, "vat": CNPJ_PRETTY})
        self.assertFalse(filho.is_company)

    def test_a_child_cannot_hold_a_document_of_its_own(self):
        """And writing one on it rewrites the PARENT's -- the trap behind the guard.

        ``vat`` is a synced commercial field: Odoo pushes it up to the
        commercial entity and back down to every descendant. So a contact
        inside a company never holds a document of its own, and typing a CNPJ
        on 'Alexandre' would silently change the Panaceia's. The rule must not
        promote him, and this is why.
        """
        mae = self.Partner.create({"name": "Grupo", "is_company": True, "vat": CNPJ_PRETTY})
        filho = self.Partner.create({"name": "Contato", "parent_id": mae.id})
        self.assertEqual(filho.vat, CNPJ_PRETTY, "the child inherits the parent's document")

        filho.vat = OTHER_CNPJ

        self.assertEqual(mae.vat, "43.828.151/0002-26",
                         "writing a document on a child rewrites the parent's")
        self.assertFalse(filho.is_company, "and still invents no company")

    def test_clearing_a_child_document_leaves_the_parent_alone(self):
        """The way out for the four contacts holding their parent's CNPJ.

        Only set values propagate upwards, so emptying the child empties the
        child. Worth a test because the opposite would be catastrophic: it
        would erase the CNPJ of the company they hang from.
        """
        mae = self.Partner.create({"name": "Panaceia", "is_company": True, "vat": CNPJ_PRETTY})
        filho = self.Partner.create({"name": "Alexandre", "parent_id": mae.id})

        filho.vat = False

        self.assertFalse(filho.vat)
        self.assertEqual(mae.vat, CNPJ_PRETTY)

    def test_an_explicit_choice_in_the_same_write_wins(self):
        """Ticking 'Individual' by hand answers the rule instead of tripping over it."""
        partner = self.Partner.create({"name": "Caso à parte"})
        partner.write({"vat": CNPJ_PRETTY, "is_company": False})
        self.assertFalse(partner.is_company)

    def test_the_rule_does_not_fire_on_unrelated_writes(self):
        """Editing the phone of a contact must not rewrite what it is."""
        partner = self.Partner.create({"name": "Caso à parte"})
        partner.write({"vat": CNPJ_PRETTY, "is_company": False})
        partner.phone = "11 99999-0000"
        self.assertFalse(partner.is_company)

    # --- a tela -----------------------------------------------------------

    def test_onchange_punctuates_and_ticks_company(self):
        form = self.Partner.new({"name": "Digitando"})
        form.vat = CNPJ_DIGITS
        form._onchange_vat_document_br()
        self.assertEqual(form.vat, CNPJ_PRETTY)
        self.assertTrue(form.is_company)

    # --- o dígito verificador --------------------------------------------

    def test_check_digits(self):
        Partner = self.Partner
        self.assertTrue(Partner._vat_is_valid_br(CNPJ_PRETTY))
        self.assertTrue(Partner._vat_is_valid_br(CPF_PRETTY))
        self.assertTrue(Partner._vat_is_valid_br("171.037.078-55"))
        self.assertFalse(Partner._vat_is_valid_br(CNPJ_BROKEN))
        self.assertFalse(Partner._vat_is_valid_br("111.111.111-11"),
                         "onze dígitos repetidos passam na conta e não são CPF")

    def test_what_is_not_a_document_is_not_judged(self):
        """Nem vat estrangeiro nem os dez quebrados são deste juiz."""
        self.assertTrue(self.Partner._vat_is_valid_br("FR12345678901"))
        self.assertTrue(self.Partner._vat_is_valid_br("346986000156"))
        self.assertTrue(self.Partner._vat_is_valid_br(""))

    def test_onchange_warns_about_a_broken_check_digit(self):
        form = self.Partner.new({"name": "Digitando"})
        form.vat = CNPJ_BROKEN
        aviso = form._onchange_vat_document_br()
        self.assertTrue(aviso and aviso.get("warning"), "tinha que avisar")
        self.assertTrue(form.is_company,
                        "e ainda assim reconhecer o CNPJ: erro de digitação não "
                        "muda o que o documento é")

    def test_onchange_warns_about_a_document_with_the_wrong_length(self):
        form = self.Partner.new({"name": "Comix"})
        form.vat = "346986000156"
        aviso = form._onchange_vat_document_br()
        self.assertTrue(aviso and aviso.get("warning"))
        self.assertIn("12", aviso["warning"]["message"])

    def test_a_valid_document_says_nothing(self):
        form = self.Partner.new({"name": "Digitando"})
        form.vat = CNPJ_DIGITS
        self.assertFalse(form._onchange_vat_document_br())

    def test_a_foreign_vat_says_nothing(self):
        form = self.Partner.new({"name": "Éditions"})
        form.vat = "FR12345678901"
        self.assertFalse(form._onchange_vat_document_br())

    def test_an_invalid_document_still_saves(self):
        """Aviso, não muro: a base ainda tem 21 documentos que não fecham."""
        partner = self.Partner.create({"name": "Legado", "vat": CNPJ_BROKEN})
        self.assertEqual(partner.vat, CNPJ_BROKEN)

    def test_onchange_unticks_company_when_a_cpf_is_typed(self):
        """What the screen should have done when the CPF was typed into TESTE."""
        form = self.Partner.new({"name": "TESTE", "is_company": True})
        form.vat = CPF_DIGITS
        form._onchange_vat_document_br()
        self.assertEqual(form.vat, CPF_PRETTY)
        self.assertFalse(form.is_company)
