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

    def test_o_relatorio_mede_quantidade_e_valor_por_livro(self):
        """O Relatório nasce da LINHA (quem sabe livro e quantidade), abre no
        gráfico, exclui cancelados e mora antes das Configurações."""
        acao = self.env.ref('liber_olist.action_olist_dashboard')
        self.assertEqual(acao.res_model, 'olist.order.line',
                         "só a linha sabe produto e quantidade")
        self.assertTrue(acao.view_mode.startswith('graph'))
        self.assertIn("Cancelado", acao.domain,
                      "cancelado contaria como venda no relatório")
        self.assertIn('f_30_dias', acao.context,
                      "sem a janela de 30 dias o gráfico vira a história toda")
        pivo = self.env.ref('liber_olist.view_olist_order_line_pivot')
        for medida in ('quantidade', 'valor_total'):
            self.assertIn(medida, pivo.arch,
                          "o pivô perdeu a medida %s" % medida)
        busca = self.env.ref('liber_olist.view_olist_order_line_search')
        self.assertIn("'livro'", busca.arch,
                      "o agrupamento usa o rótulo CURTO (ISBN · título…), "
                      "não o nome completo da ficha")
        menu = self.env.ref('liber_olist.menu_olist_dashboard')
        config = self.env.ref('liber_olist.menu_olist_config')
        self.assertLess(menu.sequence, config.sequence,
                        "o Relatório mora antes das Configurações")

    def test_a_poda_dos_botoes_nao_volta(self):
        """Poda de 19/08/2026: Gerar fatura, Ler em segundo plano e Carimbar
        rastreio saíram da fileira — o presente fatura no Importar, a fila de
        detalhe anda sozinha (cron 2/2h) e o rastreio carimba no write. Se um
        voltar, volta por decisão, não por copy-paste."""
        lista = self.env.ref('liber_olist.view_olist_order_list')
        for morto in ('action_create_invoice', 'action_queue_detail',
                      'action_stamp_tracking'):
            self.assertNotIn(morto, lista.arch,
                             "o botão podado voltou à fileira: %s" % morto)
        for vivo in ('action_read_detail', 'action_import_selected',
                     'action_consolidar_historico'):
            self.assertIn(vivo, lista.arch,
                          "a poda levou botão demais: %s" % vivo)
