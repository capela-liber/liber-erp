# -*- coding: utf-8 -*-
"""Um pedido de venda não vira consignação depois de nascido.

Em agosto/2026 apareceram 21 pedidos com nome de VENDA e `is_consignment`
ligado -- S63072, S63495 e outros. Eles somem da lista de Pedidos, somem da
Análise de vendas, não faturam, e continuam se chamando S: o comercial procura
o número, não acha, e a nota já saiu como remessa (5917). Foram R$ 43.362,50
em dois meses.

O clique não foi reconstituível: `cfop_id` não está em view nenhuma de
sale.order no prod, nenhum dos 21 veio do acerto e os campos não são
rastreados. Por isso a trava mora no `write` do modelo, e é isso que se prova
aqui -- não uma tela, mas a porta por onde toda tela passa.

A regra tem duas metades, e as duas precisam de teste:
  - pedido CONFIRMADO recusa a troca (é o caso real dos 21);
  - pedido em RASCUNHO aceita, mas o nome muda junto -- nome e bandeira nunca
    discordam.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_moves")
class TestSNaoViraC(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Livraria da Esquina", "is_company": True})
        cls.product = cls.env["product.product"].create(
            {"name": "Grande Sertão", "type": "consu", "list_price": 90.0})
        cls.prefixo_venda = cls.env["ir.sequence"].search(
            [("code", "=", "sale.order")], limit=1).prefix or "S"

    def _pedido(self, consignado=False):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "is_consignment": consignado,
            "consignment_type": "opening" if consignado else False,
            "order_line": [(0, 0, {
                "product_id": self.product.id, "product_uom_qty": 3})],
        })

    # -- caminho feliz ------------------------------------------------------
    def test_venda_nasce_com_numero_de_venda(self):
        pedido = self._pedido()
        self.assertFalse(pedido.is_consignment)
        self.assertTrue(pedido.name.startswith(self.prefixo_venda))

    def test_consignacao_nasce_com_numero_proprio(self):
        pedido = self._pedido(consignado=True)
        self.assertTrue(pedido.is_consignment)
        self.assertFalse(
            pedido.name.startswith(self.prefixo_venda),
            "Pedido C nasceu com número de venda: %s" % pedido.name)

    # -- o caso real: o erro que estava em produção -------------------------
    def test_pedido_confirmado_recusa_virar_consignacao(self):
        pedido = self._pedido()
        pedido.action_confirm()
        with self.assertRaises(UserError):
            pedido.is_consignment = True

    def test_consignacao_confirmada_recusa_virar_venda(self):
        pedido = self._pedido(consignado=True)
        # confirmar um Pedido C exige contrato ativo; a trava é anterior a isso,
        # então basta pôr o estado no ponto em que ela morde.
        pedido.state = "sale"
        with self.assertRaises(UserError):
            pedido.is_consignment = False

    # -- borda: em rascunho pode, mas o nome acompanha ----------------------
    def test_rascunho_troca_de_bandeira_e_o_nome_vai_junto(self):
        pedido = self._pedido()
        antigo = pedido.name
        pedido.is_consignment = True
        self.assertNotEqual(pedido.name, antigo)
        self.assertFalse(
            pedido.name.startswith(self.prefixo_venda),
            "trocou a bandeira e manteve o número de venda: %s" % pedido.name)

    def test_volta_para_venda_recupera_numero_de_venda(self):
        pedido = self._pedido(consignado=True)
        pedido.is_consignment = False
        self.assertTrue(pedido.name.startswith(self.prefixo_venda))

    # -- rede de baixo ------------------------------------------------------
    def test_constrains_recusa_nome_de_venda_em_consignacao(self):
        """Mesmo forçando o nome na mão, a incoerência não se salva."""
        pedido = self._pedido(consignado=True)
        with self.assertRaises(UserError):
            pedido.name = "%s99999" % self.prefixo_venda

    def test_escrita_que_nao_toca_na_bandeira_passa_ilesa(self):
        pedido = self._pedido()
        pedido.action_confirm()
        pedido.client_order_ref = "OC 1234"
        self.assertEqual(pedido.client_order_ref, "OC 1234")
