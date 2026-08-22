# -*- coding: utf-8 -*-
"""O tour do Editorial nas Compras: a porta, pela tela de verdade.

O `test_editorial_compras.py` prova o ACL no ORM. Este prova o caminho: que o
menu abre para o perfil, que o filtro "Com livros" existe e separa, e que o
pedido abre em leitura. É a diferença entre "tem direito" e "chega lá".
"""
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "liber_roles_tour")
class TestEditorialComprasTour(HttpCase):

    def test_editorial_compras_tour(self):
        company = self.env.company
        # A sessão do tour roda em inglês pelo mesmo motivo do tour dos
        # contratos: passo que só existe por texto quebra quando a tradução
        # entra. O "Com livros" é exceção consciente -- ele é escrito em
        # português na fonte, e é isso que a tela mostra nos dois idiomas.
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Editorial do Tour',
                'login': 'editorial_tour',
                'password': 'editorial_tour',
                'lang': 'en_US',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, self.env.ref(
                    'liber_roles.group_editorial_assistente').id)],
            })
        self.assertTrue(usuario.exists())

        fornecedor = self.env['res.partner'].create({'name': 'Gráfica do Tour'})
        livro = self.env['product.product'].create({
            'name': 'Livro do Tour', 'type': 'consu',
            'metabooks_book_title': 'Livro do Tour',
        })
        pedido = self.env['purchase.order'].create({
            'partner_id': fornecedor.id,
            'order_line': [(0, 0, {
                'product_id': livro.id, 'product_qty': 2000,
                'price_unit': 4.20, 'name': livro.name,
                'date_planned': '2026-09-15 00:00:00'})],
        })
        # Confirmar não é detalhe do fixture: a ação "Pedidos de compra" tem
        # domínio `state = purchase`, e cotação mora na tela ao lado. Sem isto
        # a lista abre vazia e o tour não tem o que ler -- foi o passo 5 quem
        # contou.
        pedido.button_confirm()

        self.start_tour("/odoo", "editorial_compras_tour",
                        login="editorial_tour")
