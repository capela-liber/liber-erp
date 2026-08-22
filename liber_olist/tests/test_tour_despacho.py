# -*- coding: utf-8 -*-
"""O tour da fila: a tela de verdade, no perfil de verdade.

A regra da casa (22/08/2026): ORM por função e, ao fechar, um tour que
percorre o caminho principal logado como quem vai usar. Aqui o perfil é o
funcionário comum — o ACL do módulo dá leitura a todo interno e escrita só à
gerência, então o que a equipe faz nas telas do Olist é LER: a fila, o badge
do XML, a ficha do pedido. O tour mede o que a tela pede; o ORM só mede o
que o teste pediu.
"""
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'liber_olist_tour')
class TestDespachoTour(HttpCase):

    def test_olist_despacho_tour(self):
        company = self.env.company
        # Sessão em inglês, como nos tours do liber_roles: passo que só
        # existe por texto quebra quando a tradução entra. O número do
        # pedido (TOUR-900) é dado, não tradução — por isso é ele o âncora.
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': "Equipe do Tour",
                'login': 'olist_tour',
                'password': 'olist_tour',
                'lang': 'en_US',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, self.env.ref('base.group_user').id)],
            })
        self.assertTrue(usuario.exists())

        self.env['olist.account'].search([]).write({'active': False})
        account = self.env['olist.account'].create({
            'name': "Olist Tour", 'company_id': company.id,
            'token': "TOKEN-T", 'read_only': True, 'stock_reserve': 0})
        livro = self.env['product.product'].create({
            'name': "Livro do Tour Olist", 'barcode': "9784444444441",
            'type': 'consu', 'is_storable': True, 'list_price': 30.0})
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "tour.xml",
            'olist_nota_id': '900', 'olist_account_id': account.id,
            'danfe_no': '900', 'file_create_date': '2026-08-22'})
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': livro.id,
            'ks_product_name': "Livro", 'ks_product_qty': 1,
            'ks_price': 30.0, 'ks_product_barcode': livro.barcode})
        self.env['olist.order'].create({
            'account_id': account.id, 'olist_id': 'TOUR-900',
            'numero': "TOUR-900", 'situacao': "Aprovado",
            'cliente_nome': "Comprador do Tour",
            'data_pedido': '2026-08-22', 'id_nota_fiscal': '900',
            'detalhe_lido_em': '2026-08-22 12:00:00',
            'line_ids': [(0, 0, {'codigo': livro.barcode,
                                 'descricao': "Livro", 'quantidade': 1,
                                 'valor_unitario': 30.0,
                                 'product_id': livro.id})]})

        self.start_tour("/odoo", "olist_despacho_tour", login='olist_tour')
