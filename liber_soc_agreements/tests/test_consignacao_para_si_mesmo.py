# -*- coding: utf-8 -*-
"""A casa não abre contrato de consignação consigo mesma.

Em agosto/2026 abriram-se dois: o 275 (Edlab Press, 24/08) e o 285 (n-1,
27/08), cada um com a PRÓPRIA empresa no lugar do cliente. Cada contrato ganhou
sua prateleira, e um ajuste de auditoria empurrou o estoque da casa para
dentro dela — 6.711 e 20.691 exemplares, R$ 2,08 milhões a preço de capa.

O estrago não é contábil, é operacional: livro em prateleira de consignação
não está disponível para vender. O armazém da n-1 foi a zero nos títulos
afetados e cinco pedidos da Amazon ficaram sem atendimento com o livro dentro
do prédio.

Consignação é um acordo entre DUAS partes. Cliente igual a fornecedor não é
acordo — é o mesmo estoque, com outro nome.

O recorte é ESTREITO: uma empresa do grupo consignar para OUTRA é legítimo e
acontece. O que não existe é a empresa consignar para ela mesma.
"""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_agreements")
class TestConsignacaoParaSiMesmo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.livraria = cls.env["res.partner"].create(
            {"name": "Livraria de Fora", "is_company": True})

    def _contrato(self, partner):
        return self.env["consignment.agreement"].create({
            "partner_id": partner.id,
            "company_id": self.company.id,
        })

    # -- caminho feliz ------------------------------------------------------
    def test_contrato_com_livraria_de_fora_passa(self):
        contrato = self._contrato(self.livraria)
        self.assertTrue(contrato.id)

    # -- o caso real --------------------------------------------------------
    def test_contrato_com_a_propria_empresa_recusa(self):
        with self.assertRaises(ValidationError):
            self._contrato(self.company.partner_id)

    def test_contrato_com_OUTRA_empresa_do_grupo_passa(self):
        """O recorte é estreito de propósito, e esta é a metade que prova.

        A Edlab Press deixar livro na prateleira da n-1 é consignação de
        verdade: há duas partes e o estoque muda de mãos. Uma trava que
        recusasse "qualquer empresa da casa" mataria um fluxo legítimo."""
        outra = self.env["res.company"].search(
            [("id", "!=", self.company.id)], limit=1)
        if not outra:
            self.skipTest("banco com uma empresa só")
        contrato = self._contrato(outra.partner_id)
        self.assertTrue(contrato.id)

    # -- borda: contato-filho de empresa nossa ------------------------------
    def test_contato_filho_da_propria_empresa_tambem_recusa(self):
        """A trava lê o parceiro COMERCIAL, não o contato que foi escolhido.

        Sem isso bastaria escolher um contato da própria empresa para abrir o
        mesmo buraco por uma porta lateral."""
        filho = self.env["res.partner"].create({
            "name": "Depto de Vendas",
            "parent_id": self.company.partner_id.id,
        })
        with self.assertRaises(ValidationError):
            self._contrato(filho)
