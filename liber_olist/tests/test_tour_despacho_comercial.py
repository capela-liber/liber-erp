# -*- coding: utf-8 -*-
"""O tour do comercial despachando — a tela, no perfil que ganhou o direito.

O `test_acesso_comercial` prova cada modelo pelo ORM. Este prova o clique: o
Assistente comercial marca o pedido na fila e despacha. É a diferença entre
"tem direito" e "chega lá" — e foi a tela, não o ORM, que reprovou a equipe
com "Você não tem permissões para criar registros de Espelho de pedido do
Olist" (24/08/2026).
"""
from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'liber_olist_tour')
class TestDespachoComercialTour(HttpCase):

    def test_olist_despacho_comercial_tour(self):
        company = self.env.company
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': "Assistente do Tour",
                'login': 'comercial_tour',
                'password': 'comercial_tour',
                'lang': 'en_US',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                # O perfil de verdade, não o admin: admin passa em tudo e não
                # prova nada sobre o perfil.
                'group_ids': [(4, self.env.ref(
                    'liber_roles.group_comercial_assistente').id)],
            })
        self.assertTrue(usuario.exists())

        self.env['olist.account'].search([]).write({'active': False})
        account = self.env['olist.account'].create({
            'name': "Olist Tour Comercial", 'company_id': company.id,
            'token': "TOKEN-TC", 'read_only': True, 'stock_reserve': 0})
        livro = self.env['product.product'].create({
            'name': "Livro do Comercial", 'barcode': "9788888888882",
            'type': 'consu', 'is_storable': True, 'list_price': 35.0})
        armazem = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        self.env['stock.quant'].sudo().create({
            'product_id': livro.id,
            'location_id': armazem.lot_stock_id.id,
            'inventory_quantity': 4,
        }).action_apply_inventory()
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "tour-c.xml",
            'olist_nota_id': '991', 'olist_account_id': account.id,
            'danfe_no': '991', 'file_create_date': '2026-08-24'})
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': livro.id,
            'ks_product_name': "Livro", 'ks_product_qty': 1,
            'ks_price': 35.0, 'ks_product_barcode': livro.barcode})
        self.env['olist.order'].create({
            'account_id': account.id, 'olist_id': 'TOUR-C1',
            'numero': "TOUR-C1", 'situacao': "Aprovado",
            'cliente_nome': "Comprador do Tour",
            'data_pedido': fields.Date.today(),
            'id_nota_fiscal': '991',
            'detalhe_lido_em': '2026-08-24 12:00:00',
            'line_ids': [(0, 0, {'codigo': livro.barcode,
                                 'descricao': "Livro", 'quantidade': 1,
                                 'valor_unitario': 35.0,
                                 'product_id': livro.id})]})

        self.start_tour("/odoo", "olist_despacho_comercial_tour",
                        login='comercial_tour')
