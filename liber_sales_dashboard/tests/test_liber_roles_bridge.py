# -*- coding: utf-8 -*-
"""A demonstração abre os painéis de Vendas e de Produto (12/10/2026).

Sem a ponte, a conta pública via só o painel de Faturamento: os de Vendas e
Produto são do Gerente de Vendas, que o visitante retira. O teste abre o
painel como o visitante -- é a leitura serializada que a tela pede, e é ela
que leva o mapa do Brasil quando o liber_geo_brasil está instalado.
"""
import json

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDemonstracaoVeOsPaineis(TransactionCase):

    def setUp(self):
        super().setUp()
        visitante = self.env.ref('liber_roles.group_visitante',
                                 raise_if_not_found=False)
        if not visitante:
            self.skipTest('liber_roles não está instalado nesta base')
        LOGIN = 'demo_paineis'
        self.demo = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Demo dos painéis', 'login': LOGIN, 'password': LOGIN,
                'group_ids': [(6, 0, visitante.ids)]})
        self.vendas = self.env.ref(
            'spreadsheet_dashboard_sale.spreadsheet_dashboard_sales')
        self.produto = self.env.ref(
            'spreadsheet_dashboard_sale.spreadsheet_dashboard_product')
        self.env.invalidate_all()

    def test_a_demo_ve_vendas_e_produto(self):
        vistos = self.env['spreadsheet.dashboard'].with_user(self.demo).search([])
        self.assertIn(self.vendas, vistos)
        self.assertIn(self.produto, vistos)

    def test_a_demo_abre_o_painel_de_vendas(self):
        dados = json.loads(
            self.vendas.with_user(self.demo)._get_serialized_readonly_dashboard())
        self.assertIn('snapshot', dados)

    def test_o_mapa_e_do_brasil_quando_o_geo_esta_instalado(self):
        if not self.env['ir.module.module'].search_count([
                ('name', '=', 'liber_geo_brasil'), ('state', '=', 'installed')]):
            self.skipTest('liber_geo_brasil não instalado nesta base')
        texto = self.vendas.with_user(self.demo)._get_serialized_readonly_dashboard()
        self.assertIn('br_uf', texto, 'o painel da demo saiu com o mapa-múndi')

    def test_o_gerente_continua_vendo(self):
        gerente = self.env.ref('sales_team.group_sale_manager')
        self.assertIn(gerente, self.vendas.group_ids,
                      'a ponte soma o visitante, não troca o grupo do painel')
