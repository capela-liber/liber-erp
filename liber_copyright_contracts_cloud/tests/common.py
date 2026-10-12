# -*- coding: utf-8 -*-
"""A mapped folder of the first provider installed, two contract PDFs, a
contract, and Settings pointing at the folder. No provider is called:
Cloud Files records are plain records until someone syncs or downloads."""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase

CLOUD_USER = "liber_cloud_files.group_liber_cloud_user"


def make_fixture(cls):
    providers = [key for key, _label in cls.env["liber.cloud.folder"]._fields[
        "provider"]._description_selection(cls.env)]
    if not providers:
        cls.skipTest(cls, "no Cloud Files provider installed")
    cls.provider = providers[0]
    cls.company = cls.env.company
    cls.reader_group = cls.env["res.groups"].create({"name": "Reads contracts folder"})
    cls.folder = cls.env["liber.cloud.folder"].create({
        "name": "Contratos", "provider": cls.provider,
        "path": "/contratos", "external_id": "edlab/contratos",
        "read_group_ids": [(4, cls.reader_group.id)],
    })
    cls.other_folder = cls.env["liber.cloud.folder"].create({
        "name": "Capas", "provider": cls.provider,
        "path": "/capas", "external_id": "edlab/capas",
    })
    File = cls.env["liber.cloud.file"]
    cls.pdf_main = File.create({
        "folder_id": cls.folder.id, "name": "PEREIRA_VIEIRA_SERMOES_CONTRATO.pdf",
        "path": "/contratos/PEREIRA_VIEIRA_SERMOES_CONTRATO.pdf"})
    cls.pdf_amend = File.create({
        "folder_id": cls.folder.id, "name": "PEREIRA_VIEIRA_SERMOES_ADITIVO.pdf",
        "path": "/contratos/PEREIRA_VIEIRA_SERMOES_ADITIVO.pdf"})
    cls.cover = File.create({
        "folder_id": cls.other_folder.id, "name": "capa.pdf",
        "path": "/capas/capa.pdf"})
    cls.company.contract_cloud_folder_ids = [(6, 0, cls.folder.ids)]
    today = fields.Date.today()
    cls.contract = cls.env["edlab.contract"].create({
        "signature_date": today - timedelta(days=30),
        "expiration_date": today + timedelta(days=365),
    })


class ContractCloudCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        make_fixture(cls)
