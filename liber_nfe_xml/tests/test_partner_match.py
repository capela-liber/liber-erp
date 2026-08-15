# -*- coding: utf-8 -*-
"""Matching the counterparty by CNPJ/CPF, whatever punctuation each side uses.

The NFe carries the document as bare digits; the register almost always holds
it punctuated. Comparing the two as plain strings never hit, so every note from
a punctuated customer minted a fresh partner with sudo. In `merge` that showed
up as 362 documents held by more than one family of partners - including the
house's own CNPJ, which existed twice. (Another 45 documents are shared inside
one family, which is not duplication: Odoo copies a company's vat onto its
contacts, so "Jorge Sallum" legitimately carries the Edlab CNPJ.)

The punctuation in real data is not tidy: dots in the wrong places, and one
pair differing only by a SOFT HYPHEN (U+00AD) instead of a plain one. Hence
matching on digits, not on a guessed canonical format.
"""
from odoo.tests import TransactionCase, tagged

CNPJ_DIGITS = "04354383000106"
CNPJ_PRETTY = "04.354.383/0001-06"
CPF_DIGITS = "12345678909"
CPF_PRETTY = "123.456.789-09"


@tagged("post_install", "-at_install")
class TestPartnerDocumentMatch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]
        cls.Panel = cls.env["nfe.xml.panel"]

    def test_vat_digits_is_kept_in_step_with_vat(self):
        partner = self.Partner.create({"name": "Livraria X", "vat": CNPJ_PRETTY})
        self.assertEqual(partner.vat_digits, CNPJ_DIGITS)

        partner.vat = CPF_PRETTY
        self.assertEqual(partner.vat_digits, CPF_DIGITS,
                         "the stored digits must follow an edit of vat")

        partner.vat = False
        self.assertFalse(partner.vat_digits)

    def test_punctuated_register_matches_bare_xml(self):
        """The case that was minting duplicates on every note."""
        partner = self.Partner.create({"name": "Livraria Y", "vat": CNPJ_PRETTY})

        found = self.Panel._find_or_create_partner(CNPJ_DIGITS, "Livraria Y")

        self.assertEqual(found, partner, "must reuse the punctuated register")
        self.assertEqual(
            self.Partner.search_count([("vat_digits", "=", CNPJ_DIGITS)]), 1)

    def test_bare_register_matches_punctuated_lookup(self):
        """And the other way round, for bases holding bare digits."""
        partner = self.Partner.create({"name": "Livraria Z", "vat": CNPJ_DIGITS})

        found = self.Panel._find_or_create_partner(CNPJ_PRETTY, "Livraria Z")

        self.assertEqual(found, partner)

    def test_soft_hyphen_still_matches(self):
        """Real data holds U+00AD where a hyphen belongs - invisible on screen."""
        weird = "04.354.383/0001­06"
        partner = self.Partner.create({"name": "Livraria W", "vat": weird})
        self.assertEqual(partner.vat_digits, CNPJ_DIGITS)

        found = self.Panel._find_or_create_partner(CNPJ_DIGITS, "Livraria W")

        self.assertEqual(found, partner)

    def test_misplaced_dots_still_match(self):
        """'00.300662/0001-87' and '00.300.662/0001-87' are the same company."""
        partner = self.Partner.create({
            "name": "Leitura", "vat": "00.300662/0001-87"})

        found = self.Panel._find_or_create_partner("00300662000187", "Leitura")

        self.assertEqual(found, partner)

    def test_unknown_document_still_creates(self):
        """Not finding one must keep creating it - the flow depends on that."""
        before = self.Partner.search_count([("vat_digits", "=", "11444777000161")])
        self.assertFalse(before)

        created = self.Panel._find_or_create_partner("11444777000161", "Nova Livraria")

        self.assertTrue(created)
        self.assertEqual(created.vat_digits, "11444777000161")
        self.assertTrue(created.is_company, "14 digits is a CNPJ")

    def test_no_document_finds_nothing(self):
        self.assertFalse(self.Panel._find_or_create_partner("", "Sem documento"))
        self.assertFalse(self.Partner._find_by_document("nao-tem-digito"))

    def test_child_contact_answers_with_its_company(self):
        """Odoo copies a company's vat onto its contacts.

        In `merge` the Edlab CNPJ sits on the company AND on 21 people under
        it. Matching a note against one of those people would file it under
        the contact instead of the company that issued it.
        """
        company = self.Partner.create({
            "name": "Editora Mae", "vat": CNPJ_PRETTY, "is_company": True})
        person = self.Partner.create({
            "name": "Fulano de Tal", "parent_id": company.id, "vat": CNPJ_PRETTY})
        self.assertEqual(person.vat_digits, CNPJ_DIGITS)

        found = self.Partner._find_by_document(CNPJ_DIGITS)

        self.assertEqual(found, company,
                         "the company must win over its own contact")
        self.assertNotEqual(found, person)

    def test_child_only_match_climbs_to_the_company(self):
        """If only a contact carries the document, answer with its company."""
        company = self.Partner.create({"name": "Casa Sem Vat", "is_company": True})
        person = self.Partner.create({
            "name": "Contato Com Vat", "parent_id": company.id, "vat": CNPJ_DIGITS})

        found = self.Partner._find_by_document(CNPJ_PRETTY)

        self.assertEqual(found, person.commercial_partner_id)
        self.assertEqual(found, company)

    def test_duplicates_answer_with_the_oldest(self):
        """A base that already carries duplicates must not drift between them."""
        first = self.Partner.create({"name": "Dupla A", "vat": CNPJ_PRETTY})
        second = self.Partner.create({"name": "Dupla B", "vat": CNPJ_DIGITS})
        self.assertLess(first.id, second.id)

        for _attempt in range(3):
            self.assertEqual(
                self.Partner._find_by_document(CNPJ_DIGITS), first,
                "the oldest record must win, every time")
