# -*- coding: utf-8 -*-
"""A bonificação e a feira não são venda -- nem no relatório, nem no painel.

Três operações tiram o livro do armazém sem vender: a consignação (5917), a
bonificação (5910) e a feira (5914). A consignação já saía do `sale.report`
pela marca do Pedido C (liber_soc_moves); as outras duas saem por aqui, pelo
CFOP, que é o que diz o que a operação É.

A regra vale nos dois lugares em que o dashboard de Vendas conta pedido: os
cards e os gráficos, que leem `sale.report`, e as duas tabelas do rodapé, que
leem `sale.order` direto.
"""
import json

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.liber_soc_fiscal_br.models.sale_report import NOT_REVENUE_KINDS


@tagged('post_install', '-at_install', 'soc_fiscal')
class TestBonificacaoForaDaVenda(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Livraria da Bonificação'})
        cls.product = cls.env['product.product'].create({
            'name': 'Livro Bonificado', 'type': 'consu', 'list_price': 50.0})

    def _cfop(self, code):
        cfop = self.env['nfe.cfop'].search([('code', '=', code)], limit=1)
        if not cfop:
            self.skipTest("sem o CFOP %s neste banco" % code)
        return cfop

    def _pedido(self, cfop_code=None):
        vals = {
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': self.product.id,
                                   'product_uom_qty': 3})],
        }
        if cfop_code:
            vals['cfop_id'] = self._cfop(cfop_code).id
        pedido = self.env['sale.order'].create(vals)
        # O `sale.report` é lido em SQL: sem descarregar, o `document_kind`
        # (related gravado) ainda não está na coluna e o relatório veria vazio.
        self.env.flush_all()
        return pedido

    # ------------------------------------------------------- o relatório
    def test_a_bonificacao_nao_entra_no_relatorio_de_vendas(self):
        """O livro é dado: sai do estoque e nunca vira receita."""
        bonificacao = self._pedido('5910')
        self.assertEqual(bonificacao.document_kind, 'bonus')
        achados = self.env['sale.report'].search([('partner_id', '=', self.partner.id)])
        self.assertFalse(achados)

    def test_a_venda_continua_entrando(self):
        """A guarda é estreita: o 5102 é venda e conta como sempre contou."""
        self._pedido('5102')
        achados = self.env['sale.report'].search([('partner_id', '=', self.partner.id)])
        self.assertTrue(achados)

    def test_o_acerto_continua_entrando(self):
        """O S do Acerto (5113) é a venda da consignação -- é onde vira receita."""
        self._pedido('5113')
        achados = self.env['sale.report'].search([('partner_id', '=', self.partner.id)])
        self.assertTrue(achados)

    def test_a_remessa_indefinida_nao_entra(self):
        """O 5949 é remessa: indefinida sobre qual, mas remessa (decisão de 19/08)."""
        remessa = self._pedido('5949')
        self.assertEqual(remessa.document_kind, 'transfer')
        achados = self.env['sale.report'].search([('partner_id', '=', self.partner.id)])
        self.assertFalse(achados)

    def test_pedido_sem_cfop_continua_entrando(self):
        """Vazio é "não se sabe", não é "não é venda".

        O `document_kind` vem do CFOP, que a casa começou a preencher agora:
        todo pedido mais velho está com ele vazio -- no `dev`, TODOS os 34.795.
        Filtrá-los esvaziaria o painel inteiro.
        """
        self._pedido()
        achados = self.env['sale.report'].search([('partner_id', '=', self.partner.id)])
        self.assertTrue(achados)

    # ---------------------------------------------------------- o painel
    def test_a_guarda_do_painel_carrega_as_operacoes(self):
        dashboard = self.env['spreadsheet.dashboard'].search([], limit=1)
        if not dashboard:
            self.skipTest("nenhum spreadsheet.dashboard neste banco")
        self.assertIn(['document_kind', 'not in', list(NOT_REVENUE_KINDS)],
                      dashboard._sale_order_dashboard_guards())

    def test_a_tabela_do_painel_nao_lista_bonificacao(self):
        """A tabela lê `sale.order` direto -- e ali a guarda tem de estar escrita."""
        dashboard = self.env['spreadsheet.dashboard'].search([], limit=1)
        if not dashboard:
            self.skipTest("nenhum spreadsheet.dashboard neste banco")
        bonificacao = self._pedido('5910')
        venda = self._pedido('5102')
        dashboard.spreadsheet_data = json.dumps({
            'sheets': [{'figures': []}],
            'pivots': {},
            'lists': {'1': {
                'id': '1', 'name': 'Sales Orders', 'model': 'sale.order',
                'columns': ['name', 'amount_untaxed'], 'domain': [],
                'context': {}, 'orderBy': []}},
        })
        lido = json.loads(dashboard._get_serialized_readonly_dashboard())['snapshot']
        achados = self.env['sale.order'].search(lido['lists']['1']['domain'])
        self.assertIn(venda, achados)
        self.assertNotIn(bonificacao, achados)
