# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


# `post_install`: estes testes criam `res.partner`, e este módulo carrega
# ANTES do `account` na ordem de dependências. Num banco que já tem o
# `account` instalado, a coluna `res_partner.autopost_bills` já existe como
# NOT NULL enquanto o campo (com seu default) ainda não está no registro --
# e o INSERT bate no constraint. Depois de tudo carregado, criar parceiro
# funciona normalmente.
@tagged('post_install', '-at_install')
class TestContractMultiCompanyRules(TransactionCase):
    """Um usuário só enxerga os contratos das empresas a que pertence."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "Editora A"})
        cls.company_b = cls.env["res.company"].create({"name": "Editora B"})
        cls.user_b = cls.env["res.users"].create({
            "name": "Usuária da B",
            "login": "usuaria.b@test",
            "company_id": cls.company_b.id,
            "company_ids": [(6, 0, [cls.company_b.id])],
            "group_ids": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("liber_copyright_contracts.group_contract_user").id,
            ])],
        })
        cls.author = cls.env["res.partner"].create({"name": "Autora Teste"})
        cls.work = cls.env["product.template"].create({"name": "Obra Teste"})
        cls.contract_a = cls.env["edlab.contract"].create({
            "company_id": cls.company_a.id,
            "royalty_line_ids": [(0, 0, {
                "partner_id": cls.author.id,
                "product_id": cls.work.id,
                "tier_ids": [(0, 0, {"qty_from": 0, "qty_to": 0, "percentage": 10.0})],
            })],
        })
        cls.line_a = cls.contract_a.royalty_line_ids
        cls.tier_a = cls.line_a.tier_ids

    def test_other_company_cannot_see_contract(self):
        """Caminho feliz da regra: contrato, linha e faixa da empresa A somem
        da busca de quem só pertence à empresa B."""
        Contract = self.env["edlab.contract"].with_user(self.user_b)
        self.assertNotIn(self.contract_a, Contract.search([]))
        Line = self.env["edlab.contract.royalty.line"].with_user(self.user_b)
        self.assertNotIn(self.line_a, Line.search([]))
        Tier = self.env["edlab.contract.royalty.tier"].with_user(self.user_b)
        self.assertNotIn(self.tier_a, Tier.search([]))

    def test_other_company_read_raises(self):
        """Acesso direto (leitura por id) também é barrado, não só a busca."""
        with self.assertRaises(AccessError):
            self.contract_a.with_user(self.user_b).read(["name"])
        with self.assertRaises(AccessError):
            self.line_a.with_user(self.user_b).read(["partner_id"])
        with self.assertRaises(AccessError):
            self.tier_a.with_user(self.user_b).read(["percentage"])

    def test_allowed_company_sees_contract(self):
        """Edge case: basta a empresa A entrar nas empresas PERMITIDAS do
        usuário (company_ids), sem trocar a empresa ativa, para o contrato
        aparecer."""
        self.user_b.write({"company_ids": [(4, self.company_a.id)]})
        found = self.env["edlab.contract"].with_user(self.user_b).search([])
        self.assertIn(self.contract_a, found)
        self.contract_a.with_user(self.user_b).read(["name"])  # não levanta
