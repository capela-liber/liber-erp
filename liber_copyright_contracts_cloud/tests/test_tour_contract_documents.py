# -*- coding: utf-8 -*-
"""Settings to contract on the real screen, as a contracts manager: the
Documents tab lists the linked file, the main one is marked, and the
header offers to open it."""
from odoo.tests import HttpCase, tagged

from .common import make_fixture

LOGIN = "contract_documents_tour"


@tagged("post_install", "-at_install", "copyright_cloud_tour")
class TestContractDocumentsTour(HttpCase):
    def test_contract_documents_tour(self):
        make_fixture(self)
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Contracts Manager (documents tour)",
            "login": LOGIN,
            "password": LOGIN,
            "lang": "en_US",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("liber_copyright_contracts.group_contract_manager").id,
                self.reader_group.id])],
        })
        self.assertTrue(user)
        self.env["edlab.contract.document"].create({
            "contract_id": self.contract.id, "file_id": self.pdf_main.id})
        self.env["edlab.contract.document"].create({
            "contract_id": self.contract.id, "file_id": self.pdf_amend.id,
            "note": "Aditivo"})
        url = ("/odoo/action-liber_copyright_contracts.action_edlab_contract/"
               f"{self.contract.id}")
        self.start_tour(url, "contract_documents_tour", login=LOGIN)
