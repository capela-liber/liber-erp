# -*- coding: utf-8 -*-
"""Tour do "Zerar analítico", logado como GERENTE (não admin: admin passa em
tudo e não prova nada sobre o perfil). Prova o que o ORM não vê: o botão
aparece para o gerente, a confirmação abre, e o clique chega ao fim sem
Access Error."""
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import HttpCase, tagged

LOGIN = "zerar_analitico_tour"


@tagged("post_install", "-at_install")
class TestResetAnalyticsTour(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        author = cls.env["res.partner"].create({"name": "Machado de Assis"})
        book = cls.env["product.template"].create({
            "name": "Dom Casmurro", "type": "consu", "list_price": 10.0})
        cls.contract = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [(0, 0, {
                "partner_id": author.id,
                "product_id": book.id,
                "recoupable_advance": 500.0,
            })],
        })
        cls.contract.royalty_line_ids.action_create_analytic_account()
        cls.env["res.users"].create({
            "name": "Gerente do tour", "login": LOGIN, "password": LOGIN,
            "group_ids": [Command.link(cls.env.ref("base.group_user").id),
                          Command.link(cls.env.ref(
                              "liber_copyright_contracts.group_contract_manager").id)],
        })

    def test_manager_resets_from_the_form(self):
        account = self.contract.royalty_line_ids.analytic_account_id
        AL = self.env["account.analytic.line"]
        self.assertTrue(AL.search_count([("account_id", "=", account.id)]))
        self.start_tour(
            "/odoo/action-liber_copyright_contracts.action_edlab_contract/"
            f"{self.contract.id}",
            "contract_reset_analytics_tour", login=LOGIN)
        self.assertFalse(AL.search_count([("account_id", "=", account.id)]))
