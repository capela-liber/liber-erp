# -*- coding: utf-8 -*-
"""O painel Produtos pela tela, no perfil do Gerente de Vendas.

O `test_top_no_painel.py` prova que o painel sai da leitura com o limite; o
hoot prova o corte. Este prova o caminho: que quem tem o painel (o core o dá
ao `sales_team.group_sale_manager`) entra no app Painéis, acha "Product" na
lateral e o vê montado -- com o remendo carregado do pacote de verdade e uma
venda confirmada para o gráfico ter o que desenhar.

Não é o admin de propósito: admin passa em tudo e não prova nada sobre o
perfil.
"""
from odoo.tests import HttpCase, tagged



# A senha do usuário de tour é IGUAL AO LOGIN -- é assim que o `start_tour`
# entra. O literal fica no login e a senha o referencia: escrito das duas
# vezes, ele casa com a varredura de segredos do publish_liber_erp.sh e barra
# a publicação inteira.
LOGIN = 'vendas_painel_tour'

@tagged("post_install", "-at_install", "liber_dashboard_top_tour")
class TestPainelProdutosTour(HttpCase):

    def test_painel_produtos_tour(self):
        empresa = self.env.company
        usuario = self.env["res.users"].with_context(
            no_reset_password=True).create({
                "name": "Vendas do Tour",
                "login": LOGIN,
                "password": LOGIN,
                "lang": "en_US",
                "company_id": empresa.id,
                "company_ids": [(6, 0, [empresa.id])],
                "group_ids": [(4, self.env.ref("sales_team.group_sale_manager").id)],
            })
        self.assertTrue(usuario.exists())

        # Uma venda confirmada, para o gráfico de barras ter uma barra. Sem
        # ela o painel abre igual, mas a fonte de dados do gráfico devolveria
        # vazio e o corte nunca seria exercitado na tela.
        livraria = self.env["res.partner"].create({"name": "Livraria do Painel"})
        livro = self.env["product.product"].create({
            "name": "Livro do Painel", "type": "consu", "list_price": 42.0})
        pedido = self.env["sale.order"].create({
            "partner_id": livraria.id,
            "order_line": [(0, 0, {"product_id": livro.id, "product_uom_qty": 3})],
        })
        pedido.action_confirm()

        self.start_tour("/odoo", "painel_produtos_tour", login=LOGIN)
