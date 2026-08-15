# -*- coding: utf-8 -*-
"""Mudar estado de contrato é assinatura, e assinatura é do gerente.

O assistente redige: cria e edita minutas. O que ele não pode -- validar,
cancelar, renovar -- não pode por NENHUM caminho: nem pelo botão, nem por um
write({'state': ...}) via RPC. A trava mora no ORM (write/create do modelo),
e é isso que estes testes seguram. O superusuário passa, porque os crons de
renovação e expiração mudam estado em nome do sistema.
"""
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


# `post_install`: estes testes criam `res.partner`, e este módulo carrega
# ANTES do `account` na ordem de dependências. Num banco que já tem o
# `account` instalado, a coluna `res_partner.autopost_bills` já existe como
# NOT NULL enquanto o campo (com seu default) ainda não está no registro --
# e o INSERT bate no constraint. Depois de tudo carregado, criar parceiro
# funciona normalmente.
@tagged('post_install', '-at_install')
class TestContractStatePower(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company

        def _usuario(nome, login, grupos):
            return cls.env["res.users"].with_context(
                no_reset_password=True).create({
                    "name": nome,
                    "login": login,
                    "company_id": company.id,
                    "company_ids": [(6, 0, [company.id])],
                    "group_ids": [(6, 0, [
                        cls.env.ref("base.group_user").id,
                    ] + [cls.env.ref(g).id for g in grupos])],
                })

        cls.assistente = _usuario(
            "Assistente Jurídico", "assistente.juridico@test",
            ["liber_copyright_contracts.group_contract_user"])
        cls.gerente = _usuario(
            "Gerente Jurídico", "gerente.juridico@test",
            ["liber_copyright_contracts.group_contract_manager"])

        cls.author = cls.env["res.partner"].create({"name": "Autora Teste"})
        cls.work = cls.env["product.template"].create({"name": "Obra Teste"})
        cls.contract = cls.env["edlab.contract"].create({
            "company_id": company.id,
            "royalty_line_ids": [(0, 0, {
                "partner_id": cls.author.id,
                "product_id": cls.work.id,
                "tier_ids": [(0, 0, {
                    "qty_from": 0, "qty_to": 0, "percentage": 10.0})],
            })],
        })

    def _como(self, user):
        return self.contract.with_user(user)

    # -- caminho feliz ------------------------------------------------------

    def test_gerente_valida_cancela_renova(self):
        contrato = self._como(self.gerente)
        contrato.action_validate()
        self.assertEqual(contrato.state, "valid")
        contrato.action_renew()
        self.assertEqual(contrato.state, "renewed")
        contrato.action_cancel()
        self.assertEqual(contrato.state, "cancelled")

    def test_assistente_redige(self):
        """O assistente cria a minuta e a edita -- só não assina."""
        Contract = self.env["edlab.contract"].with_user(self.assistente)
        minuta = Contract.create({
            "company_id": self.env.company.id,
            "royalty_line_ids": [(0, 0, {
                "partner_id": self.author.id,
                "product_id": self.work.id,
                "tier_ids": [(0, 0, {
                    "qty_from": 0, "qty_to": 0, "percentage": 8.0})],
            })],
        })
        self.assertEqual(minuta.state, "draft")
        minuta.write({"auto_renew": True})
        self.assertTrue(minuta.auto_renew)

    # -- o que o assistente NÃO pode ---------------------------------------

    def test_assistente_nao_confirma_pelo_botao(self):
        with self.assertRaises(AccessError):
            self._como(self.assistente).action_validate()

    def test_assistente_nao_muda_estado_por_rpc(self):
        """O caminho torto: write direto no campo, sem passar pelo botão."""
        with self.assertRaises(AccessError):
            self._como(self.assistente).write({"state": "valid"})
        with self.assertRaises(AccessError):
            self._como(self.assistente).write({"state": "cancelled"})

    def test_assistente_nao_cria_ja_confirmado(self):
        """Edge case: nascer 'valid' seria confirmar sem confirmar."""
        with self.assertRaises(AccessError):
            self.env["edlab.contract"].with_user(self.assistente).create({
                "company_id": self.env.company.id,
                "state": "valid",
            })

    # -- os caminhos que continuam abertos ---------------------------------

    def test_sistema_muda_estado(self):
        """O cron de renovação/expiração roda como superusuário e passa."""
        self.contract.sudo().write({"state": "expired"})
        self.assertEqual(self.contract.state, "expired")

    def test_config_implica_gerente_implica_usuario(self):
        """A escada dos grupos: Configuração > Administrador > Usuário."""
        config = self.env.ref("liber_copyright_contracts.group_contract_config")
        manager = self.env.ref(
            "liber_copyright_contracts.group_contract_manager")
        user = self.env.ref("liber_copyright_contracts.group_contract_user")
        self.assertIn(manager, config.implied_ids)
        self.assertIn(user, manager.implied_ids)
        self.assertIn(self.env.ref("base.user_admin"), config.user_ids)
