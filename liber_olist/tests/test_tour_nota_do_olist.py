# -*- coding: utf-8 -*-
"""O tour da nota do Olist: o livro certo chega na tela.

O `test_desconto_e_produto_da_nota` prova as duas correções pelo ORM — o
desconto que a nota declara e o livro que o produto-lixo escondia. Este prova
o que o comercial vê: despacha o pedido, abre a fatura e lê o título na linha.

Vale um tour porque os dois defeitos eram invisíveis onde nasciam e só
apareciam aqui. O produto "CFOP5102", batizado com o nome do primeiro livro
que passou, entrava calado: a fatura era postada, autorizada e paga dizendo
outro título. Quem descobriria seria o cliente, lendo a DANFE.

O cenário é o do prod: o XML traz o nome certo do livro e um produto errado, e
o espelho do Olist — que casou pelo ISBN e acertou — é quem sabe a resposta.
"""
from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'liber_olist_tour')
class TestNotaDoOlistTour(HttpCase):

    def test_olist_nota_do_olist_tour(self):
        company = self.env.company
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': "Assistente da Nota",
            'login': 'nota_olist_tour',
            'password': 'nota_olist_tour',
            'lang': 'en_US',
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            # O perfil de verdade: admin passa em tudo e não prova nada.
            'group_ids': [(4, self.env.ref(
                'liber_roles.group_comercial_assistente').id)],
        })

        self.env['olist.account'].search([]).write({'active': False})
        account = self.env['olist.account'].create({
            'name': "Olist Tour Nota", 'company_id': company.id,
            'token': "TOKEN-TNF", 'read_only': True, 'stock_reserve': 0})

        livro = self.env['product.product'].create({
            'name': "Bom crioulo do Tour", 'barcode': "9788888888899",
            'default_code': "9788888888899", 'type': 'consu',
            'is_storable': True, 'list_price': 64.90})
        # O produto-lixo: a CFOP lida como se fosse código de produto, com o
        # nome de outro livro. É este que a nota trazia no prod.
        lixo = self.env['product.product'].create({
            'name': "Os cantos do homem-sombra", 'default_code': "CFOP5102",
            'type': 'consu', 'list_price': 64.90})

        armazem = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        self.env['stock.quant'].sudo().create({
            'product_id': livro.id,
            'location_id': armazem.lot_stock_id.id,
            'inventory_quantity': 4,
        }).action_apply_inventory()

        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "tour-nf.xml",
            'olist_nota_id': '9911', 'olist_account_id': account.id,
            'danfe_no': '9911', 'file_create_date': '2026-09-05'})
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id,
            # O nome está CERTO e o produto ERRADO: é essa a assinatura do
            # defeito, e é dela que o conserto se agarra.
            'ks_product_id': lixo.id,
            'ks_product_name': "BOM CRIOULO DO TOUR",
            'ks_product_qty': 1, 'ks_price': 64.90,
            'discount_item': 6.49, 'net_price': 58.41,
            'ks_total_price': 64.90})

        self.env['olist.order'].create({
            'account_id': account.id, 'olist_id': 'TOUR-NF1', 'valor': 64.90,
            'numero': "TOUR-NF1", 'situacao': "Aprovado",
            'cliente_nome': "Leitora do Tour",
            'data_pedido': fields.Date.today(),
            'id_nota_fiscal': '9911',
            'detalhe_lido_em': '2026-09-05 12:00:00',
            'line_ids': [(0, 0, {
                'codigo': livro.barcode,
                # O espelho escreve com travessão, o XML com hífen: é a
                # diferença que a normalização do nome tem de atravessar.
                'descricao': "BOM CRIOULO — DO TOUR",
                'quantidade': 1, 'valor_unitario': 64.90,
                'product_id': livro.id})]})

        self.start_tour("/odoo", "olist_nota_do_olist_tour",
                        login='nota_olist_tour')
