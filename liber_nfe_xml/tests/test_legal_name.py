# -*- coding: utf-8 -*-
"""Two names on the record: the everyday label and the razao social.

The import used to rewrite ``partner.name`` with the xNome of every note,
which meant a branch nickname ("Travessa Botafogo") died on the next XML.
Now the xNome lands in ``legal_name`` -- the fiscal name keyed by CNPJ --
and ``name`` belongs to the house. The xFant, which the emitter block
carries and the import used to throw away, becomes the suggested name of a
record born from a note.
"""
import base64
import os

from odoo.tests import TransactionCase, tagged

CNPJ = "31.004.013/0021-06"
CNPJ_DIGITS = "31004013002106"
RAZAO = "LIVRARIA DA TRAVESSA LTDA"
FANTASIA = "Travessa Villa Lobos"
APELIDO = "Travessa Botafogo"


@tagged("post_install", "-at_install")
class TestLegalName(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]
        cls.Panel = cls.env["nfe.xml.panel"]

    def test_new_partner_gets_both_names(self):
        partner = self.Panel._find_or_create_partner(
            CNPJ_DIGITS, RAZAO, trade_name=FANTASIA)
        self.assertEqual(partner.legal_name, RAZAO)
        self.assertEqual(partner.name, FANTASIA,
                         "with an xFant on the note, the everyday name is it")

    def test_new_partner_without_fant_falls_back_to_razao(self):
        partner = self.Panel._find_or_create_partner(CNPJ_DIGITS, RAZAO)
        self.assertEqual(partner.name, RAZAO)
        self.assertEqual(partner.legal_name, RAZAO)

    def test_nickname_survives_the_next_note(self):
        """The regression this whole change exists for."""
        partner = self.Partner.create({"name": APELIDO, "vat": CNPJ})

        found = self.Panel._find_or_create_partner(CNPJ_DIGITS, RAZAO)

        self.assertEqual(found, partner)
        self.assertEqual(found.name, APELIDO,
                         "the import must not rewrite the everyday name")
        self.assertEqual(found.legal_name, RAZAO,
                         "the razao social must be healed from the note")

    def test_sync_name_off_touches_nothing(self):
        """Our own companies keep both names as filed."""
        partner = self.Partner.create({
            "name": APELIDO, "legal_name": "OUTRA RAZAO", "vat": CNPJ})

        self.Panel._find_or_create_partner(CNPJ_DIGITS, RAZAO, sync_name=False)

        self.assertEqual(partner.name, APELIDO)
        self.assertEqual(partner.legal_name, "OUTRA RAZAO")

    def test_extract_parties_reads_the_emitter_xfant(self):
        with open(os.path.join(os.path.dirname(__file__),
                               "nfe_exemplo.xml"), "rb") as handle:
            xml = handle.read()
        panel = self.Panel.create({
            "file": base64.b64encode(xml),
            "file_name": "nfe_exemplo.xml",
        })
        parties = panel._extract_parties()
        self.assertEqual(parties["emit_name"], "EDLAB PRESS EDITORA LTDA")
        self.assertEqual(parties["emit_fant"], "Edlab Press")

    def test_extract_parties_without_xfant_is_calm(self):
        """xFant is optional in the NFe schema -- its absence is not an error
        (the legacy import used to raise on it)."""
        xml = (b'<?xml version="1.0"?>'
               b'<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe>'
               b'<emit><CNPJ>31004013002106</CNPJ><xNome>%s</xNome></emit>'
               b'<dest><CNPJ>35288052000190</CNPJ><xNome>EDLAB</xNome></dest>'
               b'</infNFe></NFe>' % RAZAO.encode())
        panel = self.Panel.create({
            "file": base64.b64encode(xml), "file_name": "sem_fant.xml"})
        parties = panel._extract_parties()
        self.assertEqual(parties["emit_name"], RAZAO)
        self.assertFalse(parties["emit_fant"])
