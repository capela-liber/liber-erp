# -*- coding: utf-8 -*-
"""A cerca das faturas de royalty, travada nos dois lados.

O ir.model.access.csv deste módulo abre `account.move` em leitura para o
`group_contract_user`, e o comentário dele sempre disse a intenção: "quem tem
o app de contratos LÊ as faturas de royalty (o menu Bills é dele) sem ganhar o
Faturamento". A intenção estava certa e nunca tinha sido escrita como regra.

Medido no `testing` em 11/08/2026, antes do conserto, com um usuário real de
Editorial/Assistente: 127 de 127 lançamentos visíveis -- 62 notas de venda e
7 de compra, com valores e fornecedores. O mesmo valia para o Jurídico.

Os dois lados no mesmo arquivo de propósito. A cerca sozinha é fácil de
escrever errada de um jeito que também cega o Financeiro, e aí o conserto de
um buraco vira outro buraco: regras de grupos diferentes se combinam por OU,
e é isso que faz o Financeiro continuar vendo tudo.
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "copyright_payments")
class TestCercaDasFaturas(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        company = cls.env.company
        cls.autor = cls.env["res.partner"].create({"name": "Autora da cerca"})
        cls.contrato = cls.env["edlab.contract"].create({
            "signature_date": today - timedelta(days=30),
            "expiration_date": today + timedelta(days=365),
        })

        diario = cls.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", company.id)], limit=1)
        if not diario:
            cls.skipTest(cls, "sem diário de compras nesta base")

        def _nota(contrato=False):
            return cls.env["account.move"].create({
                "move_type": "in_invoice",
                "partner_id": cls.autor.id,
                "invoice_date": today,
                "journal_id": diario.id,
                "edlab_contract_id": contrato and cls.contrato.id or False,
            })

        cls.nota_de_royalty = _nota(contrato=True)
        cls.nota_qualquer = _nota()

        Users = cls.env["res.users"].with_context(no_reset_password=True)

        def _usuario(nome, xmlid_grupo):
            grupo = cls.env.ref(xmlid_grupo, raise_if_not_found=False)
            if not grupo:
                return None
            return Users.create({
                "name": nome, "login": "%s@cerca.test" % nome,
                "company_id": company.id, "company_ids": [(6, 0, [company.id])],
                "group_ids": [(4, cls.env.ref("base.group_user").id),
                              (4, grupo.id)],
            })

        cls.so_contratos = _usuario(
            "so_contratos", "liber_copyright_contracts.group_contract_user")
        cls.faturamento = _usuario("faturamento", "account.group_account_invoice")
        cls.env.flush_all()
        cls.env.registry.clear_cache()

    def _ve(self, usuario, nota):
        return bool(self.env(user=usuario.id, su=False)["account.move"]
                    .search_count([("id", "=", nota.id)]))

    def test_quem_so_tem_contratos_ve_so_as_faturas_de_contrato(self):
        """O buraco fechado: as duas metades numa asserção só.

        Separá-las deixaria passar o caso em que a cerca cega o usuário por
        completo -- que também seria "não vê a nota de venda", e estaria
        igualmente errado.
        """
        self.assertTrue(
            self._ve(self.so_contratos, self.nota_de_royalty),
            "quem tem o app de contratos deixou de ver a própria fatura de "
            "royalty: a cerca fechou demais e o menu Bills ficou vazio")
        self.assertFalse(
            self._ve(self.so_contratos, self.nota_qualquer),
            "quem tem só o app de contratos está vendo lançamento que não "
            "nasceu de contrato nenhum -- era esse o vazamento de 11/08/2026")

    def test_o_financeiro_continua_vendo_tudo(self):
        """O outro lado, e o motivo de ele sair de graça.

        Regras de registro de grupos diferentes se combinam por OU, não por E.
        Quem tem `account.group_account_invoice` carrega a regra nativa "All
        Journal Entries", cujo domínio é "tudo", e a união com a nossa continua
        sendo tudo. Se algum dia alguém trocar o OU por um E -- ou mover esta
        regra para um grupo que o Financeiro também tenha --, é aqui que
        aparece.
        """
        for nota, o_que in ((self.nota_de_royalty, "a fatura de royalty"),
                            (self.nota_qualquer, "o lançamento comum")):
            self.assertTrue(
                self._ve(self.faturamento, nota),
                "o Financeiro deixou de ver %s: a cerca dos contratos "
                "vazou para quem fatura" % o_que)
