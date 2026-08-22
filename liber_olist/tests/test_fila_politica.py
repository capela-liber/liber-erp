# -*- coding: utf-8 -*-
"""Despachar com ou sem nota é escolha das Definições (22/08/2026).

O desenho original exige a nota: a caixa viaja com a DANFE, e o pedido "Em
aberto" espera o Olist faturar. A política 'com ou sem nota' inverte a espera
— o pacote sai na frente e a FATURA é quem corre atrás: quando o sync arquiva
o XML, _completar_faturas_pendentes a cria e ela alcança a transferência até
já validada. O que não muda em nenhum dos mundos: a fatura só nasce do XML.
"""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFilaPolitica(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Fila", 'company_id': cls.env.company.id,
            'token': "TOKEN-Q", 'read_only': True, 'stock_reserve': 0})
        cls.livro = cls.env['product.product'].create({
            'name': "Livro da Fila", 'barcode': "9783333333335",
            'type': 'consu', 'is_storable': True, 'list_price': 40.0})
        cls.wh = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant'].sudo().create({
            'product_id': cls.livro.id,
            'location_id': cls.wh.lot_stock_id.id,
            'inventory_quantity': 10,
        }).action_apply_inventory()

    def _politica(self, valor):
        self.env['ir.config_parameter'].sudo().set_param(
            'liber_olist.despacho_politica', valor)

    def _pedido(self, olist_id, nota=None):
        return self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': olist_id,
            'numero': olist_id, 'situacao': "Aprovado",
            'cliente_nome': "Comprador da Fila",
            'data_pedido': '2026-08-21',
            'id_nota_fiscal': nota or False,
            'detalhe_lido_em': '2026-08-22 12:00:00',
            'line_ids': [(0, 0, {'codigo': self.livro.barcode,
                                 'descricao': "Livro", 'quantidade': 2,
                                 'valor_unitario': 40.0,
                                 'product_id': self.livro.id})]})

    def _painel(self, nota):
        painel = self.env['nfe.xml.panel'].create({
            'file': b"PHhtbC8+", 'file_name': "fila-%s.xml" % nota,
            'olist_nota_id': nota, 'olist_account_id': self.account.id,
            'danfe_no': nota, 'file_create_date': '2026-08-22'})
        self.env['nfe.xml.items'].create({
            'soc_xml_id': painel.id, 'ks_product_id': self.livro.id,
            'ks_product_name': "Livro", 'ks_product_qty': 2,
            'ks_price': 40.0, 'ks_product_barcode': self.livro.barcode})
        return painel

    # ---- caminho feliz: o padrão continua exigindo a nota ------------------

    def test_by_default_the_queue_wants_the_invoice(self):
        sem = self._pedido('801')
        com = self._pedido('802', nota='811')
        fila = self.env['olist.order'].search([('despachavel', '=', True)])
        self.assertIn(com, fila)
        self.assertNotIn(sem, fila)
        with self.assertRaises(UserError):
            sem._import_to_odoo()
        self.assertFalse(sem.sale_order_id)

    def test_without_invoice_policy_opens_the_queue(self):
        self._politica('sem_nota')
        sem = self._pedido('803')
        fila = self.env['olist.order'].search([('despachavel', '=', True)])
        self.assertIn(sem, fila)
        self.assertTrue(sem._import_to_odoo())
        # O pacote é da casa: venda confirmada, entrega Pronta esperando a
        # equipe embalar — e a fatura fica devendo, de propósito.
        self.assertEqual(sem.sale_order_id.state, 'sale')
        saida = sem.sale_order_id.picking_ids
        self.assertEqual(saida.state, 'assigned')
        self.assertFalse(sem.invoice_id)

    # ---- a nota que chega depois alcança o pedido --------------------------

    def test_the_late_invoice_reaches_the_validated_delivery(self):
        self._politica('sem_nota')
        pedido = self._pedido('804')
        pedido._import_to_odoo()
        saida = pedido.sale_order_id.picking_ids
        for move in saida.move_ids:
            move.quantity = move.product_uom_qty
        saida.button_validate()
        self.assertEqual(saida.state, 'done')

        # A releitura traz o id da nota; o sync arquiva o XML DEPOIS — a
        # escrita é em outro modelo e o compute armazenado fica velho: é o
        # cenário real, e é ele que o método tem de atravessar.
        pedido.id_nota_fiscal = '814'
        self._painel('814')
        completadas = self.env['olist.order']._completar_faturas_pendentes()
        self.assertEqual(completadas, 1)
        self.assertTrue(pedido.invoice_id)
        self.assertEqual(pedido.invoice_id.state, 'posted')
        if 'nfe_move_id' in saida._fields:
            # A entrega já validada ganha a nota retroativamente.
            self.assertEqual(saida.nfe_move_id, pedido.invoice_id)

    # ---- casos de borda e de erro ------------------------------------------

    def test_completion_waits_for_the_xml(self):
        self._politica('sem_nota')
        pedido = self._pedido('805')
        pedido._import_to_odoo()
        pedido.id_nota_fiscal = '815'   # nota emitida, XML ainda não veio
        self.assertEqual(
            self.env['olist.order']._completar_faturas_pendentes(), 0)
        self.assertFalse(pedido.invoice_id)

    def test_flipping_back_closes_the_queue_at_once(self):
        self._politica('sem_nota')
        sem = self._pedido('806')
        self.assertIn(sem, self.env['olist.order'].search(
            [('despachavel', '=', True)]))
        self._politica('com_nota')
        self.assertNotIn(sem, self.env['olist.order'].search(
            [('despachavel', '=', True)]))
