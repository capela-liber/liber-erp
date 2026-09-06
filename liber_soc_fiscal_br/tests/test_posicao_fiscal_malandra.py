# -*- coding: utf-8 -*-
"""Venda comum não se veste de consignação pela posição fiscal.

O dono nomeou o defeito em 06/09/2026, depois de um dia inteiro de travas que
não eram a que importava: "a única trava útil é não poder entrar em pedido de
venda e meter uma posição fiscal de consignação. Uma malandragem."

É malandragem porque FUNCIONA. O pedido continua sendo um S: aparece na lista
de Pedidos, conta na Análise de vendas, tem vendedor e comissão. E a NOTA sai
como remessa -- sem receita e sem imposto de venda. Cada lado, lido sozinho,
parece certo; a incoerência só aparece quem olhar os dois juntos, e ninguém
olha.

A trava que já existia protege o caminho oposto (o Pedido C não sai da posição
da consignação sem alguém com responsabilidade fiscal). Esta fecha a porta de
volta.

Passa quem é consignação de verdade: o Pedido C e o S do acerto -- os dois
documentos da operação.

E a mesma porta, na NOTA (liber_nfe_remessa): uma fatura no diário de vendas
não pode levar a posição fiscal da remessa. É o que o dono chamou de "saída
simbólica que virou lançamento" -- a NF-e sai como remessa, a nota conta como
venda, e ninguém a baixa.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_fiscal")
class TestPosicaoFiscalMalandra(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create(
            {"name": "Livraria da Malandragem", "is_company": True})
        cls.product = cls.env["product.product"].create(
            {"name": "Macunaíma", "type": "consu", "list_price": 50.0})

        Posicao = cls.env["account.fiscal.position"]
        cls.fp_consignacao = Posicao.create(
            {"name": "Remessa em consignação (teste)",
             "company_id": cls.company.id})
        cls.fp_venda = Posicao.create(
            {"name": "Venda normal (teste)", "company_id": cls.company.id})
        cls.company.consignment_shipment_fiscal_position_id = cls.fp_consignacao

    def _pedido(self, **extra):
        vals = {
            "partner_id": self.partner.id,
            "order_line": [(0, 0, {"product_id": self.product.id,
                                   "product_uom_qty": 2})],
        }
        vals.update(extra)
        return self.env["sale.order"].create(vals)

    # -- a malandragem ------------------------------------------------------
    def test_venda_com_posicao_de_consignacao_recusa(self):
        with self.assertRaises(UserError):
            self._pedido(fiscal_position_id=self.fp_consignacao.id)

    def test_nem_depois_de_criado(self):
        """A porta lateral: nascer limpo e ser vestido depois."""
        pedido = self._pedido(fiscal_position_id=self.fp_venda.id)
        with self.assertRaises(UserError):
            pedido.fiscal_position_id = self.fp_consignacao

    # -- quem é consignação de verdade passa --------------------------------
    def test_pedido_c_pode_usar_a_posicao_da_consignacao(self):
        pedido = self._pedido(is_consignment=True,
                              consignment_type="opening",
                              fiscal_position_id=self.fp_consignacao.id)
        self.assertEqual(pedido.fiscal_position_id, self.fp_consignacao)

    def test_o_s_do_acerto_pode_usar(self):
        """O acerto cria um sale.order SEM a bandeira -- ele É a venda.

        Se a trava olhasse só `is_consignment`, ela recusaria justamente o
        documento em que a consignação vira receita."""
        if 'consignment.settlement' not in self.env:
            self.skipTest("sem liber_soc_settlement")
        acerto = self.env['consignment.settlement'].create(
            {"partner_id": self.partner.id, "company_id": self.company.id})
        pedido = self._pedido(consignment_operation_id=acerto.id,
                              fiscal_position_id=self.fp_consignacao.id)
        self.assertFalse(pedido.is_consignment)
        self.assertEqual(pedido.fiscal_position_id, self.fp_consignacao)

    # -- borda: venda com posição de venda passa incólume -------------------
    def test_venda_com_posicao_de_venda_passa(self):
        pedido = self._pedido(fiscal_position_id=self.fp_venda.id)
        self.assertEqual(pedido.fiscal_position_id, self.fp_venda)

    def test_venda_sem_posicao_nenhuma_passa(self):
        """Sem posição fiscal não há o que conferir, e a maioria dos pedidos
        da casa é assim."""
        pedido = self._pedido(fiscal_position_id=False)
        self.assertFalse(pedido.fiscal_position_id)

    # -- a mesma malandragem, na nota ---------------------------------------
    def _diario(self, remessa):
        return self.env["account.journal"].create({
            "name": "Remessa (teste)" if remessa else "Vendas (teste)",
            "code": "RMT" if remessa else "VDT", "type": "sale",
            "company_id": self.company.id,
            "is_remessa": remessa, "remessa_kind": "consignment",
        })

    def _nota(self, diario, posicao):
        return self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "journal_id": diario.id,
            "fiscal_position_id": posicao.id,
            "invoice_date": "2026-09-06",
            "invoice_line_ids": [(0, 0, {"product_id": self.product.id,
                                         "quantity": 1, "price_unit": 50.0})],
        })

    def test_nota_de_venda_com_posicao_de_remessa_recusa(self):
        with self.assertRaises(UserError):
            self._nota(self._diario(remessa=False), self.fp_consignacao)

    def test_nem_ao_postar_um_rascunho_antigo(self):
        """O rascunho que nasceu antes da trava não passa pelo constrains ao
        postar -- o `action_post` tem de conferir de novo."""
        nota = self._nota(self._diario(remessa=False), self.fp_venda)
        # Veste a posição de remessa por baixo do constrains, como um dado
        # antigo que já estava assim.
        self.env.cr.execute(
            "UPDATE account_move SET fiscal_position_id = %s WHERE id = %s",
            (self.fp_consignacao.id, nota.id))
        nota.invalidate_recordset()
        with self.assertRaises(UserError):
            nota.action_post()

    def test_nota_no_diario_de_remessa_passa(self):
        nota = self._nota(self._diario(remessa=True), self.fp_consignacao)
        self.assertEqual(nota.fiscal_position_id, self.fp_consignacao)

    def test_nota_de_venda_com_posicao_de_venda_passa(self):
        nota = self._nota(self._diario(remessa=False), self.fp_venda)
        self.assertEqual(nota.state, "draft")
