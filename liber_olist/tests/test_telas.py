# -*- coding: utf-8 -*-
"""Cada tela abre a SUA lista.

O modelo `olist.product` tem duas listas, e elas respondem perguntas
diferentes: a do menu Estoque compara os dois saldos (Olist × Odoo), a do
menu Produtos casa livro por ISBN. Uma ação sem view amarrada deixa o Odoo
escolher entre as duas — e foi o que aconteceu em 18/08/2026: o menu Estoque
abria a lista do catálogo, sem as colunas de quantidade, e o dono procurou
os números numa tela que nunca os teve.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTelasDoOlist(TransactionCase):
    def _lista_da_acao(self, xmlid):
        acao = self.env.ref('liber_olist.%s' % xmlid)
        vinculos = self.env['ir.actions.act_window.view'].search([
            ('act_window_id', '=', acao.id), ('view_mode', '=', 'list')])
        self.assertTrue(
            vinculos, "a ação %s não amarra lista nenhuma: o Odoo escolhe "
                      "entre as duas do modelo" % xmlid)
        return vinculos[0].view_id

    def test_estoque_abre_a_lista_da_comparacao(self):
        lista = self._lista_da_acao('action_olist_product')

        self.assertEqual(
            lista, self.env.ref('liber_olist.view_olist_product_list'))
        for campo in ('saldo_olist', 'odoo_qty', 'qty_to_send', 'divergencia'):
            self.assertIn(campo, lista.arch,
                          "a tela de estoque tem de mostrar %s" % campo)

    def test_produtos_abre_a_lista_do_catalogo(self):
        lista = self._lista_da_acao('action_olist_catalog')

        self.assertEqual(
            lista, self.env.ref('liber_olist.view_olist_catalog_list'))

    def test_as_duas_telas_nao_mostram_a_mesma_lista(self):
        self.assertNotEqual(
            self._lista_da_acao('action_olist_product'),
            self._lista_da_acao('action_olist_catalog'),
            "Estoque e Produtos respondem perguntas diferentes")

    def test_o_painel_abre_no_grafico_de_vendas(self):
        """A abertura do app é o painel: barras por dia, empilhadas por
        canal, últimos 30 dias — e cancelado não é venda."""
        acao = self.env.ref('liber_olist.action_olist_dashboard')
        self.assertTrue(acao.view_mode.startswith('graph'),
                        "o painel tem de abrir no gráfico, não numa lista")
        self.assertIn("'cancelado'", acao.domain,
                      "cancelado contaria como venda no painel")
        self.assertIn('f_30_dias', acao.context,
                      "sem a janela de 30 dias o gráfico vira a história toda")
        grafico = self.env.ref('liber_olist.view_olist_order_graph')
        for campo in ('data_pedido', 'canal', 'valor'):
            self.assertIn(campo, grafico.arch,
                          "o gráfico perdeu o eixo/medida %s" % campo)
        menu = self.env.ref('liber_olist.menu_olist_dashboard')
        self.assertEqual(menu.sequence, 1,
                         "o painel tem de ser a primeira tela da abertura")
