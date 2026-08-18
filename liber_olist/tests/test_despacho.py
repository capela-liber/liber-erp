# -*- coding: utf-8 -*-
"""O despacho é da CASA, não do status do Olist (decisão do dono, 18/08/2026).

O furo que motivou tudo: quando a etiqueta nasce, o Olist marca "Enviado" e
lava as mãos — o PDF cai na nossa mão e o pacote continua na prateleira até a
coleta. Logo "Enviado" não prova saída; só "Entregue" prova. A importação
confirma a venda e deixa a entrega PRONTA (a fila de embalagem); concluir é o
clique do funcionário — e o push de estoque desconta o reservado, senão o
marketplace revende o exemplar que espera coleta.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDespachoDaCasa(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Despacho", 'company_id': cls.env.company.id,
            'token': "TOKEN-D", 'read_only': True,
            'stock_reserve': 0,
            'order_stock_cutoff': '2026-01-01'})
        cls.livro = cls.env['product.product'].create({
            'name': "Livro do Despacho", 'barcode': "9782222222229",
            'type': 'consu', 'is_storable': True, 'list_price': 50.0})
        cls.wh = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant'].sudo().create({
            'product_id': cls.livro.id,
            'location_id': cls.wh.lot_stock_id.id,
            'inventory_quantity': 10,
        }).action_apply_inventory()
        cls.cliente = cls.env['res.partner'].create({'name': "Comprador D"})

    def _pedido(self, olist_id, situacao, nota='700'):
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "%s.xml" % olist_id,
            'olist_nota_id': nota, 'olist_account_id': self.account.id,
            'partner_id': self.cliente.id, 'danfe_no': nota,
            'file_create_date': '2026-08-15'})
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': self.livro.id,
            'ks_product_name': "Livro", 'ks_product_qty': 2,
            'ks_price': 50.0, 'ks_product_barcode': self.livro.barcode})
        return self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': olist_id,
            'numero': olist_id, 'situacao': situacao,
            'data_pedido': '2026-08-15', 'id_nota_fiscal': nota,
            'detalhe_lido_em': '2026-08-18 12:00:00',
            'line_ids': [(0, 0, {'codigo': self.livro.barcode,
                                 'descricao': "Livro", 'quantidade': 2,
                                 'valor_unitario': 50.0,
                                 'product_id': self.livro.id})]})

    def test_enviado_e_etiqueta_nao_saida(self):
        """Caminho central: 'Enviado' importa com a entrega PRONTA — a fila
        de embalagem —, sem baixar a prateleira, e gritando no filtro."""
        antes = self.livro.product_tmpl_id._olist_wh_qty(self.account)
        pedido = self._pedido('D-1', 'Enviado')
        self.assertTrue(pedido.a_despachar,
                        "com nota e sem importar, já é a despachar")
        pedido._import_to_odoo()
        entregas = pedido.sale_order_id.picking_ids
        self.assertTrue(entregas)
        self.assertTrue(all(p.state != 'done' for p in entregas),
                        "'Enviado' é etiqueta, não saída: nada a concluir")
        self.assertEqual(
            self.livro.product_tmpl_id._olist_wh_qty(self.account), antes,
            "a prateleira só baixa quando o funcionário valida")
        self.assertTrue(pedido.a_despachar, "o grito continua até a coleta")

    def test_validar_e_o_clique_que_cala_o_grito(self):
        pedido = self._pedido('D-2', 'Enviado', nota='701')
        pedido._import_to_odoo()
        pedido._concluir_entregas()          # o funcionário embalou e validou
        self.assertTrue(all(p.state == 'done'
                            for p in pedido.sale_order_id.picking_ids))
        self.assertFalse(pedido.a_despachar)

    def test_entregue_prova_que_saiu_e_conclui_sozinho(self):
        pedido = self._pedido('D-3', 'Entregue', nota='702')
        self.assertFalse(pedido.a_despachar,
                         "Entregue não é a despachar nem antes de importar")
        pedido._import_to_odoo()
        self.assertTrue(all(p.state == 'done'
                            for p in pedido.sale_order_id.picking_ids),
                        "o comprador recebeu: fato consumado, conclui")

    def test_a_releitura_reconcilia_o_esquecimento(self):
        """Caso de erro humano: embalou, coletaram, ninguém validou. Quando o
        Olist disser Entregue, o Odoo se corrige pela fonte."""
        pedido = self._pedido('D-4', 'Enviado', nota='703')
        pedido._import_to_odoo()
        self.assertTrue(any(p.state != 'done'
                            for p in pedido.sale_order_id.picking_ids))
        pedido.write({'situacao': 'Entregue'})
        self.assertTrue(all(p.state == 'done'
                            for p in pedido.sale_order_id.picking_ids))
        self.assertFalse(pedido.a_despachar)

    def test_sem_nota_nao_ha_o_que_despachar(self):
        pedido = self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': 'D-5',
            'numero': 'D-5', 'situacao': 'Em aberto',
            'data_pedido': '2026-08-15', 'id_nota_fiscal': '0'})
        self.assertFalse(pedido.a_despachar)

    def test_anterior_ao_corte_e_historia_nao_fila(self):
        self.account.order_stock_cutoff = '2026-08-16'
        pedido = self._pedido('D-6', 'Enviado', nota='704')
        self.assertFalse(pedido.a_despachar)

    def test_o_push_desconta_o_reservado(self):
        """O pacote que espera coleta ainda conta no armazém — mas tem dono.
        Oferecê-lo ao Olist seria vender o mesmo exemplar duas vezes."""
        template = self.livro.product_tmpl_id
        livre_antes = template._olist_stock_qty(self.account)
        pedido = self._pedido('D-7', 'Enviado', nota='705')
        pedido._import_to_odoo()             # confirma: reserva 2, não baixa
        self.assertEqual(template._olist_reservado_qty(self.account), 2)
        self.assertEqual(template._olist_stock_qty(self.account),
                         livre_antes - 2,
                         "o reservado saiu da oferta sem sair do armazém")
