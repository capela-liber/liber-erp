# -*- coding: utf-8 -*-
"""Tour dos meses de fechamento, logado como ASSISTENTE de contratos (não
admin: admin passa em tudo e não prova nada sobre o perfil)."""
from odoo import Command
from odoo.tests import HttpCase, tagged

LOGIN = "meses_fechamento_tour"


@tagged("post_install", "-at_install")
class TestSettlementTour(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contract = cls.env["edlab.contract"].create({})
        cls.env["res.users"].create({
            "name": "Assistente do tour", "login": LOGIN, "password": LOGIN,
            "lang": "en_US",
            "group_ids": [Command.link(cls.env.ref("base.group_user").id),
                          Command.link(cls.env.ref(
                              "liber_copyright_contracts.group_contract_user").id)],
        })

    def test_assistant_marks_closing_months(self):
        self.start_tour(
            "/odoo/action-liber_copyright_contracts.action_edlab_contract/"
            f"{self.contract.id}",
            "contract_settlement_months_tour", login=LOGIN)
        self.assertEqual(self.contract.settlement_month_ids.mapped("number"), [6, 12])
        self.assertEqual(self.contract.settlement_periodicity, "semiannual")
