# -*- coding: utf-8 -*-
"""Tests for the manual NFe import wizard.

What is being pinned down here is the wizard's *report*: before, it returned
None and closed, so a ZIP of uppercase '.XML' files, a duplicate and a corrupt
member were all indistinguishable from a clean run. Every test asserts on the
counters the user actually sees.
"""
import base64
import io
import zipfile

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .test_nfe_xml import KEY_1, KEY_2, NS, nfe_xml

KEY_3 = "35260111222333000181550010000007891000007890"


def cancel_event_xml(key, tp_evento="110111"):
    """A procEventoNFe cancelling ``key``."""
    return ("""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe xmlns="%(ns)s" versao="1.00">
  <evento versao="1.00">
    <infEvento Id="ID%(tp)s%(key)s01">
      <chNFe>%(key)s</chNFe>
      <tpEvento>%(tp)s</tpEvento>
      <dhEvento>2026-01-20T10:00:00-03:00</dhEvento>
      <descEvento>Cancelamento</descEvento>
      <xJust>Erro de digitacao nos dados do destinatario</xJust>
    </infEvento>
  </evento>
  <retEvento versao="1.00">
    <infEvento><nProt>135260000000009</nProt></infEvento>
  </retEvento>
</procEventoNFe>""" % {"ns": NS, "key": key, "tp": tp_evento}).encode()


def make_zip(members):
    """``members`` is a list of (name, bytes)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, payload in members:
            zf.writestr(name, payload)
    return buf.getvalue()


@tagged("post_install", "-at_install")
class TestImportXmlWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Panel = cls.env["nfe.xml.panel"]
        cls.Wizard = cls.env["import.xml.file"]

    def _wizard(self, blobs):
        """A wizard with ``blobs`` = list of (filename, raw bytes) attached."""
        attachments = self.env["ir.attachment"].create([{
            "name": name,
            "datas": base64.b64encode(payload),
        } for name, payload in blobs])
        return self.Wizard.create({"attachment_ids": [(6, 0, attachments.ids)]})

    # --- happy path ---------------------------------------------------------

    def test_zip_reports_what_it_imported(self):
        """A clean ZIP reports the count and links the created notes."""
        blob = make_zip([("nota1.xml", nfe_xml(KEY_1)),
                         ("nota2.xml", nfe_xml(KEY_2))])
        wizard = self._wizard([("lote.zip", blob)])

        wizard.import_xml_file()

        self.assertEqual(wizard.state, "done")
        self.assertEqual(len(wizard.panel_ids), 2)
        self.assertIn("2 note(s) imported", wizard.summary)
        self.assertFalse(wizard.failure_details)
        self.assertEqual(
            set(wizard.panel_ids.mapped("key")), {KEY_1, KEY_2})

    def test_loose_xml_is_accepted(self):
        """The commonest case - one XML mailed by the supplier - must work.

        It used to raise "not a valid ZIP archive".
        """
        wizard = self._wizard([("nota.xml", nfe_xml(KEY_1))])

        wizard.import_xml_file()

        self.assertEqual(len(wizard.panel_ids), 1)
        self.assertEqual(wizard.panel_ids.key, KEY_1)
        self.assertIn("1 note(s) imported", wizard.summary)

    def test_uppercase_xml_inside_zip_is_read(self):
        """SEFAZ portals ship '.XML'; that ZIP used to import zero, silently."""
        blob = make_zip([("NOTA1.XML", nfe_xml(KEY_1))])
        wizard = self._wizard([("lote.zip", blob)])

        wizard.import_xml_file()

        self.assertEqual(len(wizard.panel_ids), 1,
                         "uppercase .XML must be imported, not ignored")

    # --- edge cases ---------------------------------------------------------

    def test_duplicate_is_counted_not_hidden(self):
        """A note already in the panel is reported as such, not dropped mute."""
        self.Panel._ingest_xml(nfe_xml(KEY_1), "ja-importada.xml")
        blob = make_zip([("nota1.xml", nfe_xml(KEY_1)),
                         ("nota2.xml", nfe_xml(KEY_2))])
        wizard = self._wizard([("lote.zip", blob)])

        wizard.import_xml_file()

        self.assertEqual(len(wizard.panel_ids), 1)
        self.assertIn("1 note(s) imported", wizard.summary)
        self.assertIn("1 already in the panel", wizard.summary)
        self.assertEqual(self.Panel.search_count([("key", "=", KEY_1)]), 1)

    def test_non_xml_members_are_counted(self):
        """A ZIP with a stray PDF says so instead of pretending it was empty."""
        blob = make_zip([("nota1.xml", nfe_xml(KEY_1)),
                         ("danfe.pdf", b"%PDF-1.4 fake")])
        wizard = self._wizard([("lote.zip", blob)])

        wizard.import_xml_file()

        self.assertEqual(len(wizard.panel_ids), 1)
        self.assertIn("1 non-XML file(s) ignored", wizard.summary)

    def test_cancellation_event_is_applied(self):
        """A cancellation in the same ZIP flags the note it cancels."""
        blob = make_zip([("nota1.xml", nfe_xml(KEY_1)),
                         ("evento.xml", cancel_event_xml(KEY_1))])
        wizard = self._wizard([("lote.zip", blob)])

        wizard.import_xml_file()

        self.assertIn("1 cancellation(s) applied", wizard.summary)
        panel = self.Panel.search([("key", "=", KEY_1)])
        self.assertTrue(panel.is_cancelled,
                        "the second pass must flag the note as cancelled")

    # --- the failure that used to eat the whole batch -----------------------

    def test_corrupt_member_does_not_lose_the_batch(self):
        """One unreadable XML must not roll back the notes already read.

        This is the regression that mattered: the old wizard turned any
        exception into UserError, aborting the transaction and throwing away
        every note imported in the same click.
        """
        blob = make_zip([("nota1.xml", nfe_xml(KEY_1)),
                         ("lixo.xml", b"<nfeProc><<< truncated"),
                         ("nota2.xml", nfe_xml(KEY_2))])
        wizard = self._wizard([("lote.zip", blob)])

        wizard.import_xml_file()

        self.assertEqual(len(wizard.panel_ids), 2,
                         "the two good notes must survive the bad one")
        self.assertIn("1 unreadable", wizard.summary)

    def test_failed_file_is_named(self):
        """A file that fails is named, not summarised as a raw Python error."""
        wizard = self._wizard([("contrato.docx", b"PK\x03\x04 not really a zip")])

        wizard.import_xml_file()

        self.assertFalse(wizard.panel_ids)
        self.assertIn("contrato.docx", wizard.failure_details or "")

    def test_nothing_attached_is_an_error(self):
        """Clicking Import with no file still tells the user what to do."""
        wizard = self.Wizard.create({})
        with self.assertRaises(UserError):
            wizard.import_xml_file()
