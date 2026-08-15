# -*- coding: utf-8 -*-
"""O cartão da estante mostra o livro, não o código de barras.

Pedido da direção em 10/08/2026: "pode tirar o ISBN daqui; na busca já
localizamos, ninguém sabe de cor para filtrar lendo".

O ponto destes testes não é o que saiu — é o que NÃO saiu junto. A linha do
ISBN vem do kanban do core (`product`), compartilhado com Vendas ▸ Produtos e
Inventário ▸ Produtos. Herdar direto teria tirado o código de todo mundo, e
ninguém notaria até o dia em que alguém do depósito procurasse por ele.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestKanbanLivros(TransactionCase):

    def _arch(self, xmlid):
        view = self.env.ref(xmlid)
        return self.env['product.template'].get_view(
            view_id=view.id, view_type='kanban')['arch']

    def test_o_isbn_sai_do_cartao_da_estante(self):
        arch = self._arch('liber_metabooks_integration.view_metabooks_books_kanban')
        self.assertNotIn(
            'default_code', arch,
            'o ISBN voltou ao cartão de Livros')
        # o cartão sem o resto não seria um cartão
        self.assertIn('list_price', arch, 'o preço sumiu do cartão')
        self.assertIn('name="name"', arch, 'o título sumiu do cartão')

    def test_o_kanban_padrao_de_produto_fica_como_estava(self):
        """A metade que importa: a mudança é DAQUI, não do Odoo inteiro.

        Se um dia alguém trocar o `mode="primary"` da variante por uma herança
        comum "para simplificar", este teste é quem avisa que Vendas e
        Inventário perderam o código do produto junto.
        """
        arch = self._arch('product.product_template_kanban_view')
        self.assertIn(
            'default_code', arch,
            'o kanban padrão de produto perdeu o código: a variante da estante '
            'vazou para Vendas e Inventário')

    def test_a_estante_aponta_para_a_variante(self):
        """Sem esta ligação a variante existe e não é usada por ninguém."""
        acao = self.env.ref('liber_metabooks_integration.action_metabooks_books')
        variante = self.env.ref(
            'liber_metabooks_integration.view_metabooks_books_kanban')
        kanban = acao.view_ids.filtered(lambda v: v.view_mode == 'kanban')
        self.assertEqual(kanban.view_id, variante,
                         'a ação Livros não usa a variante do kanban')
        # lista e formulário seguem os padrão, de propósito
        for modo in ('list', 'form'):
            outra = acao.view_ids.filtered(lambda v: v.view_mode == modo)
            self.assertFalse(
                outra.view_id,
                'a ação Livros fixou uma view de %s; era para seguir a padrão'
                % modo)
