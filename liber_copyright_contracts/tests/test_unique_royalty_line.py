# -*- coding: utf-8 -*-
from psycopg2.errors import UniqueViolation

from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger


# `post_install`: estes testes criam `res.partner`, e este módulo carrega
# ANTES do `account` na ordem de dependências. Num banco que já tem o
# `account` instalado, a coluna `res_partner.autopost_bills` já existe como
# NOT NULL enquanto o campo (com seu default) ainda não está no registro --
# e o INSERT bate no constraint. Depois de tudo carregado, criar parceiro
# funciona normalmente.
@tagged('post_install', '-at_install')
class TestUniqueRoyaltyLine(TransactionCase):
    """A unicidade beneficiário+obra por contrato vive num models.Constraint
    (no v19 o `_sql_constraints` é ignorado pelo ORM — este teste garante que
    a constraint realmente chega ao banco)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = cls.env["res.partner"].create({"name": "Autora Teste"})
        cls.work = cls.env["product.template"].create({"name": "Obra Teste"})
        cls.contract = cls.env["edlab.contract"].create({
            "company_id": cls.env.company.id,
            "royalty_line_ids": [(0, 0, {
                "partner_id": cls.author.id,
                "product_id": cls.work.id,
            })],
        })

    @mute_logger("odoo.sql_db")
    def test_duplicate_line_rejected(self):
        """Mesmo beneficiário + mesma obra no mesmo contrato: o banco recusa."""
        with self.assertRaises(UniqueViolation), self.cr.savepoint():
            self.env["edlab.contract.royalty.line"].create({
                "contract_id": self.contract.id,
                "partner_id": self.author.id,
                "product_id": self.work.id,
            })

    def test_same_pair_in_other_contract_ok(self):
        """Caminho feliz: o par pode se repetir em OUTRO contrato."""
        other = self.env["edlab.contract"].create({
            "company_id": self.env.company.id,
            "royalty_line_ids": [(0, 0, {
                "partner_id": self.author.id,
                "product_id": self.work.id,
            })],
        })
        self.assertEqual(len(other.royalty_line_ids), 1)
