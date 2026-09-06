# -*- coding: utf-8 -*-
"""O que a nota vendeu: líquido dos itens, sem frete, gravado na nota.

"Vendemos quanto em agosto?" é pergunta de gerente de vendas, e a resposta
mora nos itens da NF-e: capa menos desconto, vezes quantidade. O total da
DANFE (`danfe_value`) carrega o frete e por isso não serve de manchete. O
Painel de Notas Fiscais externo sempre somou assim; aqui o número passa a
existir na própria nota, gravado, para o painel Vendas × Notas somar sem
abrir os itens.
"""
import base64

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "nfe_xml")
class TestLiquidoDaNota(TransactionCase):

    def _nota(self, itens, frete=0.0):
        nota = self.env["nfe.xml.panel"].create({
            "file": base64.b64encode(b"<nfe/>"), "file_name": "nota.xml",
            "danfe_value": sum(n * q for n, q, _ in itens) + frete,
            "shipping_price": frete,
        })
        for net, qty, capa in itens:
            self.env["nfe.xml.items"].create({
                "soc_xml_id": nota.id, "ks_product_name": "Livro",
                "ks_product_qty": qty, "ks_price": capa,
                "discount_item": capa - net, "net_price": net,
            })
        return nota

    def test_liquido_e_capa_menos_desconto_vezes_quantidade(self):
        nota = self._nota([(30.0, 2, 50.0), (45.0, 1, 45.0)])
        self.assertEqual(nota.net_value, 105.0)
        self.assertEqual(nota.book_qty, 3.0)

    def test_o_frete_fica_de_fora(self):
        """A DANFE diz 125; a nota vendeu 105. É a diferença entre o total
        da nota e o que o gerente chama de venda."""
        nota = self._nota([(30.0, 2, 50.0), (45.0, 1, 45.0)], frete=20.0)
        self.assertEqual(nota.danfe_value, 125.0)
        self.assertEqual(nota.net_value, 105.0)

    def test_editar_um_item_recalcula(self):
        """Sem o depends nos itens, o gravado ficaria com o valor antigo --
        a mesma doença que o `ks_total_price` já teve."""
        nota = self._nota([(30.0, 2, 50.0)])
        nota.panel_items[0].ks_product_qty = 5
        self.assertEqual(nota.net_value, 150.0)
        self.assertEqual(nota.book_qty, 5.0)

    def test_nota_sem_item_vale_zero(self):
        nota = self._nota([])
        self.assertEqual(nota.net_value, 0.0)
        self.assertEqual(nota.book_qty, 0.0)
