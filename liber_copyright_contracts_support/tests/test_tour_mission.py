# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

from .common import make_fixture

LOGIN = "author_mission_tour"


@tagged("post_install", "-at_install", "copyright_support_tour")
class TestAuthorMissionTour(HttpCase):
    def test_author_mission_tour(self):
        make_fixture(self)
        self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Royalties and Support (tour)",
            "login": LOGIN, "password": LOGIN, "lang": "en_US",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref("account.group_account_invoice").id,
                self.env.ref("liber_copyright_contracts.group_contract_manager").id])],
        })
        self.mission.action_send()
        self.mission._cron_send_queue()
        url = ("/odoo/action-liber_copyright_contracts_support.action_author_mission/"
               f"{self.mission.id}")
        self.start_tour(url, "author_mission_tour", login=LOGIN)
