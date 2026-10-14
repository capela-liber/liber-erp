# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .common import CLOUD_USER, ContractCloudCase
from odoo.addons.liber_copyright_contracts_cloud.models.contract import _normal


@tagged("post_install", "-at_install", "copyright_cloud")
class TestContractDocuments(ContractCloudCase):

    def _link(self, file, **vals):
        return self.env["edlab.contract.document"].create(
            dict(vals, contract_id=self.contract.id, file_id=file.id))

    def test_first_document_is_main_and_fills_location(self):
        doc = self._link(self.pdf_main)
        self.assertTrue(doc.is_main)
        self.assertEqual(doc.name, "PEREIRA_VIEIRA_SERMOES_CONTRATO.pdf")
        self.assertEqual(doc.path, "/contratos/PEREIRA_VIEIRA_SERMOES_CONTRATO.pdf")
        self.assertTrue(doc.provider)
        self.assertEqual(self.contract.location, doc.name)
        self.assertEqual(self.contract.main_document_id, doc)
        amend = self._link(self.pdf_amend, note="Aditivo 2024")
        self.assertFalse(amend.is_main)
        self.assertEqual(self.contract.document_count, 2)
        self.assertEqual(self.contract.location, doc.name)

    def test_switching_main_moves_location(self):
        main = self._link(self.pdf_main)
        amend = self._link(self.pdf_amend)
        amend.is_main = True
        self.assertFalse(main.is_main)
        self.assertEqual(self.contract.main_document_id, amend)
        self.assertEqual(self.contract.location, amend.name)

    def test_new_main_demotes_the_previous(self):
        main = self._link(self.pdf_main)
        amend = self._link(self.pdf_amend, is_main=True)
        self.assertFalse(main.is_main)
        self.assertEqual(self.contract.main_document_id, amend)
        self.assertEqual(self.contract.location, amend.name)

    @mute_logger("odoo.sql_db")
    def test_same_file_twice_refused(self):
        self._link(self.pdf_main)
        with self.assertRaises(Exception), self.cr.savepoint():
            self._link(self.pdf_main)

    def test_removing_main_promotes_the_next(self):
        main = self._link(self.pdf_main)
        amend = self._link(self.pdf_amend)
        main.unlink()
        self.assertTrue(amend.is_main)
        self.assertEqual(self.contract.location, amend.name)

    def test_allowed_folders_follow_settings(self):
        self.assertEqual(self.contract.allowed_cloud_folder_ids, self.folder.ids)
        settings = self.env["res.config.settings"].create({})
        settings.contract_cloud_folder_ids = [(4, self.other_folder.id)]
        settings.execute()
        self.contract.invalidate_recordset(["allowed_cloud_folder_ids"])
        self.assertEqual(sorted(self.contract.allowed_cloud_folder_ids),
                         sorted((self.folder | self.other_folder).ids))

    def test_storage_narrows_the_folders(self):
        providers = [k for k, _l in self.env["res.company"]._selection_contract_cloud_provider()]
        self.assertIn(self.provider, providers)
        settings = self.env["res.config.settings"].create({})
        settings.contract_cloud_provider = self.provider
        settings._onchange_contract_cloud_provider()
        self.assertEqual(settings.contract_cloud_folder_ids, self.folder)
        settings.execute()
        self.assertEqual(self.company.contract_cloud_provider, self.provider)
        others = [p for p in providers if p != self.provider]
        if others:
            settings = self.env["res.config.settings"].create({})
            settings.contract_cloud_provider = others[0]
            settings._onchange_contract_cloud_provider()
            self.assertFalse(settings.contract_cloud_folder_ids)
            # A folder of another storage left behind does not count.
            self.company.write({"contract_cloud_provider": others[0],
                                "contract_cloud_folder_ids": [(6, 0, self.folder.ids)]})
            self.contract.invalidate_recordset(["allowed_cloud_folder_ids"])
            self.assertFalse(self.contract.allowed_cloud_folder_ids)

    def test_normal_name(self):
        self.assertEqual(_normal(" Sermões_Vieira.PDF "), "sermoes_vieira")
        self.assertEqual(_normal("contrato v1.2"), "contrato v1.2")
        self.assertEqual(_normal(False), "")

    def test_location_check_lists_what_is_not_linked(self):
        self.contract.location = ("PEREIRA_VIEIRA_SERMOES_CONTRATO.pdf; "
                                  "PEREIRA_VIEIRA_SERMOES_ADITIVO.pdf; SUMIU.pdf")
        self.assertEqual(self.contract.location_missing,
                         "PEREIRA_VIEIRA_SERMOES_CONTRATO.pdf; "
                         "PEREIRA_VIEIRA_SERMOES_ADITIVO.pdf; SUMIU.pdf")
        self._link(self.pdf_main)
        self._link(self.pdf_amend)
        self.assertEqual(self.contract.location_missing, "SUMIU.pdf")
        Contract = self.env["edlab.contract"]
        self.assertIn(self.contract, Contract.search([("location_missing", "!=", False)]))
        self.contract.location = ("PEREIRA_VIEIRA_SERMOES_CONTRATO.pdf; "
                                  "PEREIRA_VIEIRA_SERMOES_ADITIVO.pdf")
        self.assertFalse(self.contract.location_missing)
        self.assertNotIn(self.contract, Contract.search([("location_missing", "!=", False)]))
        self.assertIn(self.contract, Contract.search([("location_missing", "=", False)]))
        with self.assertRaises(UserError):
            Contract.search([("location_missing", "ilike", "x")])

    def test_open_goes_through_the_folder_gate(self):
        doc = self._link(self.pdf_main)
        outsider = new_test_user(
            self.env, login="contract_outsider",
            groups="base.group_user,liber_copyright_contracts.group_contract_user")
        reader = new_test_user(
            self.env, login="contract_reader",
            groups="base.group_user,liber_copyright_contracts.group_contract_user")
        reader.group_ids = [(4, self.reader_group.id),
                            (4, self.env.ref(CLOUD_USER).id)]
        # The list reads for both: the line carries its own copy.
        self.env.invalidate_all()
        self.assertEqual(doc.with_user(outsider).name, doc.name)
        self.assertEqual(self.contract.with_user(outsider).location, doc.name)
        # Opening is the gate.
        with self.assertRaises(AccessError):
            doc.with_user(outsider).action_open()
        client = type("C", (), {"temporary_link": lambda self, f: "https://example/tmp"})()
        with patch.object(type(self.folder), "_client", lambda self: client):
            action = doc.with_user(reader).action_open()
            self.assertEqual(action["url"], "https://example/tmp")
            action = self.contract.with_user(reader).action_open_main_document()
            self.assertEqual(action["type"], "ir.actions.act_url")

    def test_open_without_document_explains(self):
        with self.assertRaises(UserError):
            self.contract.action_open_main_document()

    def test_contract_form_reads_for_a_user_without_the_folder(self):
        """The whole form, as the web client asks for it, for someone who
        cannot read the folder: the reason the line copies the file's name."""
        self._link(self.pdf_main)
        outsider = new_test_user(
            self.env, login="contract_outsider2",
            groups="base.group_user,liber_copyright_contracts.group_contract_user")
        self.env.invalidate_all()
        Contract = self.env["edlab.contract"].with_user(outsider)
        view = Contract.get_views([(False, "form")])["views"]["form"]
        self.assertIn("document_ids", view["arch"])
        spec = {
            "document_ids": {"fields": {"name": {}, "provider": {}, "is_main": {}}},
            "location": {}, "allowed_cloud_folder_ids": {},
            "main_document_id": {"fields": {"display_name": {}}}}
        data = Contract.browse(self.contract.id).web_read(spec)
        self.assertEqual(data[0]["document_ids"][0]["name"],
                         "PEREIRA_VIEIRA_SERMOES_CONTRATO.pdf")
