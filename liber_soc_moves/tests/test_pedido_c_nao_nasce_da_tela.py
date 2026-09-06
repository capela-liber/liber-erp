# -*- coding: utf-8 -*-
"""O Pedido C não nasce da tela de Pedidos de consignação.

A consignação tem UM documento de origem: a Operação de Consignação (CO). Dela
saem o Pedido C (C000), o Acerto (S000) e a Devolução. Um Pedido C digitado
direto na lista é um documento sem operação por trás -- e foi assim que 51
"reposições" entraram à mão em agosto/2026, sem acerto nenhum (R$ 99.205,38).

Houve um dia inteiro de travas que não eram esta: grupo de "quem abre
consignação", regra de "reposição exige acerto". O dono cortou: "só remover o
Novo da tela de Pedidos. Só isso." Não é questão de perfil -- ninguém cria
este documento à mão, porque ele não é o primeiro de nada.

O que se prova aqui é a ação (o `create: False` no contexto) e que o motor
continua aceitando o Pedido C que a CO cria. O sumiço do botão na tela quem
prova é o tour (`pedido_c_tour.js`).
"""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_moves")
class TestPedidoCNaoNasceDaTela(TransactionCase):

    def test_a_lista_de_pedidos_c_nao_tem_novo(self):
        acao = self.env.ref("liber_soc_moves.action_consignment_sale_order")
        contexto = eval(acao.context)
        self.assertIs(contexto.get("create"), False,
                      "a lista de Pedidos C voltou a oferecer o 'Novo'")
        # E continua sendo a lista dos Pedidos C, não outra coisa.
        self.assertTrue(contexto.get("default_is_consignment"))

    def test_o_motor_continua_criando_o_pedido_c(self):
        """`create: False` é da tela. A CO cria pelo motor, e o motor aceita
        de qualquer usuário -- não há grupo nem regra de negócio no create."""
        partner = self.env["res.partner"].create(
            {"name": "Livraria da Operação", "is_company": True})
        product = self.env["product.product"].create(
            {"name": "Grande Sertão", "type": "consu", "list_price": 90.0})
        pedido = self.env["sale.order"].create({
            "partner_id": partner.id,
            "is_consignment": True,
            "consignment_type": "opening",
            "order_line": [(0, 0, {"product_id": product.id,
                                   "product_uom_qty": 5})],
        })
        self.assertTrue(pedido.is_consignment)
        self.assertTrue(pedido.name.startswith("C"),
                        "o Pedido C nasceu fora da série C: %s" % pedido.name)

    def test_nao_existe_mais_o_grupo_de_abertura(self):
        """A porta por perfil foi removida de propósito: se voltar, alguém
        reinstalou a trava errada."""
        self.assertFalse(
            self.env["ir.model.data"].search([
                ("module", "=", "liber_soc_moves"),
                ("name", "=", "group_consignment_opening")]),
            "o grupo 'Open consignment by hand' voltou")
