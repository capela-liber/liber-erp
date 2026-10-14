# -*- coding: utf-8 -*-
"""O botão "Zerar analítico" do contrato (14/10/2026).

Apaga o que o sistema gerou nas contas analíticas do contrato -- apuração,
adiantamento, corte de pagamento -- e deixa o que nasceu de lançamento
contábil. É de gerente: a trava está no método, porque esconder o botão não
segura um RPC."""
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "copyright_analytics")
class TestResetAnalytics(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.author = cls.env["res.partner"].create({"name": "Machado de Assis"})
        cls.book = cls.env["product.template"].create({
            "name": "Dom Casmurro", "type": "consu", "list_price": 10.0})
        cls.contract = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
            "royalty_line_ids": [(0, 0, {
                "partner_id": cls.author.id,
                "product_id": cls.book.id,
                "recoupable_advance": 500.0,
                "tier_ids": [(0, 0, {"qty_from": 0, "qty_to": 0, "percentage": 10.0})],
            })],
        })
        cls.line = cls.contract.royalty_line_ids
        # cria a conta e, de carona, o lançamento do adiantamento
        cls.line.action_create_analytic_account()
        cls.account = cls.line.analytic_account_id
        cls.AL = cls.env["account.analytic.line"]
        # uma apuração "de fatura", como o preencher grava
        cls.accrual = cls.AL.create({
            "name": "10.00%", "account_id": cls.account.id,
            "auto_account_id": cls.account.id, "amount": -30.0,
            "date": today, "partner_id": cls.author.id,
            "company_id": cls.line.company_id.id,
        })
        cls.manager = cls.env["res.users"].create({
            "name": "Gerente DA", "login": "gerente_da_reset",
            "group_ids": [Command.link(cls.env.ref("base.group_user").id),
                          Command.link(cls.env.ref(
                              "liber_copyright_contracts.group_contract_manager").id)],
        })
        cls.assistant = cls.env["res.users"].create({
            "name": "Assistente DA", "login": "assistente_da_reset",
            "group_ids": [Command.link(cls.env.ref("base.group_user").id),
                          Command.link(cls.env.ref(
                              "liber_copyright_contracts.group_contract_user").id)],
        })

    def _generated(self):
        return self.AL.search(self.contract._edlab_resettable_analytic_domain())

    def test_manager_erases_generated_entries(self):
        """Caminho feliz: apuração e adiantamento somem, o saldo vai a zero,
        e a conversa do contrato registra o que foi apagado."""
        self.assertEqual(len(self._generated()), 2)
        result = self.contract.with_user(self.manager).action_reset_analytics()
        self.assertEqual(result["params"]["type"], "success")
        self.assertFalse(self._generated())
        self.assertFalse(self.accrual.exists())
        self.assertEqual(self.contract.edlab_royalty_balance, 0.0)
        self.assertIn("2", self.contract.message_ids[0].body)

    def test_fill_rebuilds_after_reset(self):
        """O que se zera, o preencher refaz: o adiantamento volta."""
        self.contract.with_user(self.manager).action_reset_analytics()
        self.contract.action_fill_royalty_lines()
        advance = self.AL.search([("edlab_advance_line_id", "=", self.line.id)])
        self.assertEqual(advance.amount, 500.0)

    def test_entries_from_journal_items_stay(self):
        """Edge: o que nasceu de lançamento contábil (uma conta de royalty
        paga, um lançamento manual) espelha os livros e fica."""
        company = self.line.company_id
        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", company.id)], limit=1)
        accounts = self.env["account.account"].with_company(company).search(
            [("account_type", "=", "expense")], limit=1) | \
            self.env["account.account"].with_company(company).search(
            [("account_type", "=", "liability_current")], limit=1)
        if not journal or len(accounts) < 2:
            self.skipTest("banco sem plano de contas para um lançamento manual")
        move = self.env["account.move"].create({
            "journal_id": journal.id, "company_id": company.id,
            "line_ids": [
                Command.create({"account_id": accounts[0].id, "debit": 40.0,
                                "analytic_distribution": {str(self.account.id): 100}}),
                Command.create({"account_id": accounts[1].id, "credit": 40.0}),
            ],
        })
        move.action_post()
        booked = self.AL.search([("move_line_id", "in", move.line_ids.ids)])
        self.assertEqual(len(booked), 1)
        # O core grava a distribuição na coluna do PLANO; a família lê pelo
        # account_id. Carimbá-lo aqui garante que é o move_line_id, e não a
        # sorte de cair em outra coluna, que protege o lançamento.
        booked.account_id = self.account
        self.contract.with_user(self.manager).action_reset_analytics()
        self.assertTrue(booked.exists())
        self.assertFalse(self._generated())

    def test_nothing_to_reset_warns(self):
        """Edge: contrato já zerado avisa, em vez de fingir que fez algo."""
        self.contract.with_user(self.manager).action_reset_analytics()
        result = self.contract.with_user(self.manager).action_reset_analytics()
        self.assertEqual(result["params"]["type"], "warning")

    def test_assistant_is_refused(self):
        """Erro: o assistente não zera, nem por RPC."""
        with self.assertRaises(AccessError):
            self.contract.with_user(self.assistant).action_reset_analytics()
        self.assertEqual(len(self._generated()), 2)
