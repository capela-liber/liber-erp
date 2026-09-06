# -*- coding: utf-8 -*-
"""O CFOP não pode desmentir o documento — nos dois sentidos.

A constrains já recusava o caso "CFOP de consignação num pedido de venda". A
metade que faltava era a inversa, e foi ela que sangrou em agosto/2026: um
Pedido C carregando CFOP de VENDA. O pedido ficava consignado, a nota saía
como remessa (5917), e o dinheiro nunca aparecia no faturamento — R$ 43.362,50
em dois meses, invisíveis para o comercial e para a Análise de vendas.

O domínio do campo é a trava barata (a lista já não oferece o que não cabe);
a constrains é a rede de baixo, para quem chega por importação ou RPC. Aqui se
prova a rede — o domínio se prova na tela.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "soc_fiscal")
class TestCfopRecortado(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Livraria Cultura", "is_company": True})
        cls.product = cls.env["product.product"].create(
            {"name": "Os Sertões", "type": "consu", "list_price": 70.0})
        Cfop = cls.env["nfe.cfop"]
        cls.cfop_venda = Cfop.search(
            [("document_kind", "=", "sale")], limit=1) or Cfop.create(
                {"code": "5102", "document_kind": "sale"})
        cls.cfop_remessa = Cfop.search(
            [("document_kind", "=", "consignment")], limit=1) or Cfop.create(
                {"code": "5917", "document_kind": "consignment"})

    def _pedido(self, consignado=False):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "is_consignment": consignado,
            "consignment_type": "opening" if consignado else False,
            "order_line": [(0, 0, {
                "product_id": self.product.id, "product_uom_qty": 2})],
        })

    # -- caminho feliz ------------------------------------------------------
    def test_venda_aceita_cfop_de_venda(self):
        pedido = self._pedido()
        pedido.cfop_id = self.cfop_venda
        self.assertEqual(pedido.document_kind, "sale")

    def test_pedido_c_aceita_cfop_de_remessa(self):
        pedido = self._pedido(consignado=True)
        pedido.cfop_id = self.cfop_remessa
        self.assertEqual(pedido.document_kind, "consignment")

    # -- a metade que faltava ----------------------------------------------
    def test_pedido_c_recusa_cfop_de_venda(self):
        pedido = self._pedido(consignado=True)
        with self.assertRaises(UserError):
            pedido.cfop_id = self.cfop_venda

    # -- a metade que já existia, para não regredir -------------------------
    def test_venda_recusa_cfop_de_remessa(self):
        pedido = self._pedido()
        with self.assertRaises(UserError):
            pedido.cfop_id = self.cfop_remessa

    # -- borda: CFOP vazio não opina ---------------------------------------
    def test_cfop_vazio_nao_bloqueia_nada(self):
        """Indefinido é indefinido: a constrains não adivinha documento."""
        pedido = self._pedido(consignado=True)
        pedido.cfop_id = False
        self.assertFalse(pedido.document_kind)
