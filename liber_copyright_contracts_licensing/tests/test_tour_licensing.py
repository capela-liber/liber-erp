# -*- coding: utf-8 -*-
"""Tour do licenciamento, logado como GERENTE de contratos com Faturamento
(o perfil de quem emite a licença) -- não admin: admin passa em tudo e não
prova nada sobre o perfil."""
from odoo import Command
from odoo.tests import HttpCase, tagged

from .common import LicensingCommon

LOGIN = "licenciamento_tour"


@tagged("post_install", "-at_install", "copyright_licensing")
class TestLicensingTour(LicensingCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_licensing()
        cls.env["res.partner"].create({"name": "Editora Didática Tour"})
        cls.env["res.users"].create({
            "name": "Gerente do tour", "login": LOGIN, "password": LOGIN,
            "lang": "en_US",
            "group_ids": [
                Command.link(cls.env.ref("base.group_user").id),
                Command.link(cls.env.ref(
                    "liber_copyright_contracts.group_contract_manager").id),
                Command.link(cls.env.ref("account.group_account_invoice").id),
            ],
        })

    def test_manager_issues_a_licence_from_the_contract(self):
        self.start_tour(
            "/odoo/action-liber_copyright_contracts.action_edlab_contract/"
            f"{self.contract.id}",
            "copyright_licensing_tour", login=LOGIN)
        move = self.contract.edlab_license_invoice_ids
        self.assertEqual(len(move), 1)
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.partner_id.name, "Editora Didática Tour")
        line = move.invoice_line_ids
        self.assertAlmostEqual(line.price_unit, 1000.0, places=2)
        self.assertEqual(line.account_id, self.income)
        self.assertEqual(line.analytic_distribution, {str(self.account.id): 100.0})
