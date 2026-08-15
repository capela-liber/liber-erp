# -*- coding: utf-8 -*-
"""O desconto aparece: no campo e na coluna.

A decisão está em `models/res_groups.py`. O que este teste segura é que ela
continua valendo depois de qualquer `-u` -- e, principalmente, que ela produz
o efeito pelo qual foi tomada: uma venda pela lista de preços sai com o preço
de tabela CHEIO e o percentual no campo próprio, não com o preço já líquido.
"""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDescontoVisivel(TransactionCase):

    def test_a_opcao_descontos_esta_ligada(self):
        self.assertTrue(
            self.env["product.pricelist.item"]._is_discount_feature_enabled(),
            "a opção 'Descontos' voltou a ficar desligada: o percentual da "
            "lista volta a se diluir no preço unitário")

    def test_a_lista_de_precos_vira_percentual_e_nao_preco_menor(self):
        produto = self.env["product.product"].create({
            "name": "Livro da Decisão", "type": "consu", "list_price": 100.0})
        lista = self.env["product.pricelist"].create({
            "name": "55% (fixture da casa)",
            "company_id": self.env.company.id,
            "item_ids": [(0, 0, {
                "applied_on": "3_global",
                "compute_price": "percentage",
                "percent_price": 55.0})],
        })
        parceiro = self.env["res.partner"].create({
            "name": "Distribuidora da Decisão", "is_company": True})
        parceiro.with_company(self.env.company).property_product_pricelist = lista

        pedido = self.env["sale.order"].create({
            "partner_id": parceiro.id,
            "order_line": [(0, 0, {
                "product_id": produto.id, "product_uom_qty": 1})],
        })
        linha = pedido.order_line
        self.assertEqual(linha.price_unit, 100.0,
                         "o preço saiu já líquido: o desconto se diluiu")
        self.assertEqual(linha.discount, 55.0,
                         "o percentual da lista não chegou ao campo Desc.%")
        self.assertAlmostEqual(linha.price_subtotal, 45.0, places=2)

        # E até a fatura, que é onde a casa foi ver e não achou.
        pedido.action_confirm()
        linha.qty_delivered = 1
        fatura = pedido._create_invoices()
        linha_fat = fatura.invoice_line_ids.filtered(
            lambda l: l.product_id == produto)
        self.assertEqual(linha_fat.price_unit, 100.0)
        self.assertEqual(linha_fat.discount, 55.0,
                         "a INV saiu sem o desconto no campo próprio")
        self.assertAlmostEqual(linha_fat.price_subtotal, 45.0, places=2)

    def test_a_coluna_desconto_aparece_na_fatura(self):
        """Ligar a opção acende a coluna no pedido, mas não na fatura: a do
        core nasce `optional="hide"` e não pende de grupo nenhum."""
        from lxml import etree
        arch = self.env["account.move"].get_view(
            view_id=self.env.ref("account.view_move_form").id,
            view_type="form")["arch"]
        # Lê o atributo do PRÓPRIO elemento (não uma fatia de texto em volta):
        # uma coluna vizinha com `optional` diferente daria falso positivo.
        achado = None
        for node in etree.fromstring(arch).iter("field"):
            if node.get("name") == "discount" and node.getparent().tag == "list":
                achado = node.get("optional")
        self.assertEqual(
            achado, "show",
            "a coluna Desc.% da fatura voltou a nascer escondida")
