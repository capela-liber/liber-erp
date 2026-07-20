# -*- coding: utf-8 -*-
"""Tests for the NFe XML panel: parsing, the 44-digit access key and the
XML<->invoice link.

No fixture file exists (and none is needed): each test builds a minimal
synthetic NFe in memory. The parser requires the portalfiscal namespace, an
``nfeProc`` root and the access key under ``protNFe`` — everything else is
the smallest set of tags the ``update_*`` parsers read.
"""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

NS = "http://www.portalfiscal.inf.br/nfe"

KEY_1 = "35260111222333000181550010000001231000001236"
KEY_2 = "35260111222333000181550010000004561000004567"


def nfe_xml(key, nnf="123", vnf="150.00", qty="10.0000", vun="15.00",
            emit_cnpj="11222333000181", dest_cnpj="99888777000166"):
    return ("""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="%(ns)s" versao="4.00">
  <NFe>
    <infNFe Id="NFe%(key)s" versao="4.00">
      <ide><mod>55</mod><serie>1</serie><nNF>%(nnf)s</nNF>
        <dhEmi>2026-01-15T10:00:00-03:00</dhEmi></ide>
      <emit><CNPJ>%(emit)s</CNPJ><xNome>Editora Emitente</xNome>
        <enderEmit><CEP>01310100</CEP></enderEmit></emit>
      <dest><CNPJ>%(dest)s</CNPJ><xNome>Livraria Destino</xNome>
        <enderDest><CEP>04538133</CEP></enderDest></dest>
      <det nItem="1">
        <prod><cProd>SKU1</cProd><cEAN>7891234567895</cEAN>
          <xProd>Livro Teste</xProd><CFOP>5102</CFOP>
          <qCom>%(qty)s</qCom><vUnCom>%(vun)s</vUnCom>
          <vProd>%(vnf)s</vProd></prod>
      </det>
      <total><ICMSTot><vNF>%(vnf)s</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
  <protNFe><infProt><chNFe>%(key)s</chNFe><nProt>135260000000001</nProt></infProt></protNFe>
</nfeProc>""" % {
        "ns": NS, "key": key, "nnf": nnf, "vnf": vnf, "qty": qty,
        "vun": vun, "emit": emit_cnpj, "dest": dest_cnpj,
    }).encode()


@tagged("post_install", "-at_install")
class TestNfeXml(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Panel = cls.env["nfe.xml.panel"]

    def test_ingest_parses_fields(self):
        """_ingest_xml accepts a minimal NFe and the import parses the fields."""
        panel = self.Panel._ingest_xml(nfe_xml(KEY_1), "test.xml")
        self.assertTrue(panel, "a valid NFe must create a panel")
        self.assertEqual(panel.key, KEY_1)
        self.assertEqual(panel.status, "imported")

        panel.action_import_xml_file()
        self.assertEqual(
            panel.status, "valid",
            "import failed: %s" % (panel.message_ids[:1].body or ""))
        self.assertAlmostEqual(panel.danfe_value, 150.0, places=2)
        self.assertEqual(str(panel.file_create_date), "2026-01-15")
        # the parser stores CNPJs formatted
        self.assertEqual(panel.vendor_cnpj, "11.222.333/0001-81")
        self.assertEqual(panel.customer_cnpj, "99.888.777/0001-66")
        self.assertEqual(len(panel.panel_items), 1)
        self.assertEqual(panel.panel_items.ks_product_qty, 10.0)

    def test_ingest_dedups_same_key(self):
        """Re-ingesting the same access key is a no-op (returns False)."""
        first = self.Panel._ingest_xml(nfe_xml(KEY_1), "a.xml")
        self.assertTrue(first)
        second = self.Panel._ingest_xml(nfe_xml(KEY_1), "b.xml")
        self.assertFalse(second, "same chNFe must not create a second panel")
        self.assertEqual(self.Panel.search_count([("key", "=", KEY_1)]), 1)

    def test_ingest_rejects_non_nfe(self):
        """XML that is not an NFe (or has no protNFe key) is skipped."""
        self.assertFalse(self.Panel._ingest_xml(b"<foo>bar</foo>", "x.xml"))
        self.assertFalse(self.Panel._ingest_xml(b"not xml at all", "y.xml"))

    def test_move_key_must_have_44_digits(self):
        """account.move.nfe_key accepts exactly 44 digits, nothing else."""
        partner = self.env["res.partner"].create({"name": "Cliente NFe"})
        with self.assertRaises(ValidationError):
            self.env["account.move"].create({
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "nfe_key": "123",
            })
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "nfe_key": KEY_1,
        })
        self.assertEqual(move.nfe_key, KEY_1)

    def test_move_links_panel_by_key(self):
        """The move finds its XML by access key, not by a hard db id."""
        panel = self.Panel._ingest_xml(nfe_xml(KEY_1), "link.xml")
        partner = self.env["res.partner"].create({"name": "Cliente NFe"})
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "nfe_key": KEY_1,
        })
        self.assertEqual(move.nfe_xml_panel_id, panel)
        # a different key links nothing
        move2 = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "nfe_key": KEY_2,
        })
        self.assertFalse(move2.nfe_xml_panel_id)

    def test_two_moves_cannot_share_key(self):
        """Two live moves of the same type cannot carry the same access key."""
        partner = self.env["res.partner"].create({"name": "Cliente NFe"})
        self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "nfe_key": KEY_1,
        })
        with self.assertRaises(ValidationError):
            self.env["account.move"].create({
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "nfe_key": KEY_1,
            })
