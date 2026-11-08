# -*- coding: utf-8 -*-
"""O pedido de venda leva o desconto do Olist (29/10/2026).

O Painel lê o pedido de venda. Ele nascia com o preço bruto e desconto zero,
e a venda do site aparecia sem o desconto que a nota declara (S67320: 286,06
no Painel, 55,40 de desconto na nota). Ou o contrário: com o desconto da
lista de preços do parceiro, que o Olist não deu.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDescontoNoPedido(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Desconto", 'company_id': cls.env.company.id,
            'token': "TOKEN-D", 'read_only': True})
        cls.livros = cls.env['product.product'].create([
            {'name': "Livro %s" % i, 'barcode': "97885771500%s" % i,
             'type': 'consu', 'list_price': 50.0} for i in range(5)])
        cls.parceiro = cls.env['res.partner'].create({'name': "Comprador"})

    def _pedido(self, desconto, precos):
        return self.env['olist.order'].create({
            'account_id': self.account.id, 'valor': 100.0,
            'olist_id': 'D%s' % desconto, 'numero': 'D%s' % desconto,
            'situacao': "Aprovado", 'data_pedido': '2026-10-27',
            'valor_desconto': desconto,
            'line_ids': [(0, 0, {
                'codigo': livro.barcode, 'descricao': livro.name,
                'product_id': livro.id, 'quantidade': 1,
                'valor_unitario': preco})
                for livro, preco in zip(self.livros, precos)]})

    def _venda(self, pedido):
        """O pedido de venda montado pelos mesmos valores do import."""
        venda = self.env['sale.order'].create({
            'partner_id': self.parceiro.id,
            'order_line': [(0, 0, l._sale_line_vals()) for l in pedido.line_ids]})
        pedido.sale_order_id = venda
        return venda

    def test_the_order_of_s67320_closes_with_the_net_of_the_note(self):
        # Os números do S67320: 286,06 de mercadoria, 55,40 de desconto.
        pedido = self._pedido(55.40, [44.90, 41.46, 79.90, 64.90, 54.90])
        venda = self._venda(pedido)
        self.assertTrue(all(l.price_unit in (44.90, 41.46, 79.90, 64.90, 54.90)
                            for l in venda.order_line),
                        "o preço segue bruto: é por ele que a fatura casa")
        self.assertEqual(set(venda.order_line.mapped('discount')), {19.37})
        # Porcentagem de duas casas: o centavo pode escapar, não mais que isso.
        self.assertAlmostEqual(venda.amount_untaxed, 286.06 - 55.40, delta=0.05)

    def test_without_olist_discount_the_pricelist_discount_does_not_enter(self):
        lista = self.env['product.pricelist'].create({
            'name': "Lista 20%", 'item_ids': [(0, 0, {
                'applied_on': '3_global', 'compute_price': 'percentage',
                'percent_price': 20.0})]})
        self.parceiro.property_product_pricelist = lista
        pedido = self._pedido(0.0, [50.0])
        venda = self._venda(pedido)
        self.assertEqual(venda.order_line.discount, 0.0)
        self.assertAlmostEqual(venda.amount_untaxed, 50.0, 2)

    def test_past_orders_get_the_discount_and_only_once(self):
        pedido = self._pedido(10.0, [60.0, 40.0])
        venda = self._venda(pedido)
        # Como os pedidos nasciam até esta versão: desconto zero.
        venda.order_line.write({'discount': 0.0})
        mudadas = pedido._acertar_desconto_no_pedido()
        self.assertEqual(mudadas, venda.order_line)
        self.assertEqual(set(venda.order_line.mapped('discount')), {10.0})
        self.assertAlmostEqual(venda.amount_untaxed, 90.0, 2)
        self.assertFalse(pedido._acertar_desconto_no_pedido(),
                         "rodar de novo não pode mexer em nada")

    def test_a_locked_order_is_fixed_and_stays_locked(self):
        pedido = self._pedido(10.0, [100.0])
        venda = self._venda(pedido)
        venda.order_line.write({'discount': 0.0})
        venda.action_confirm()
        venda.action_lock()
        pedido._acertar_desconto_no_pedido()
        self.assertEqual(venda.order_line.discount, 10.0)
        self.assertTrue(venda.locked)

    def test_a_free_order_does_not_divide_by_zero(self):
        pedido = self._pedido(5.0, [0.0])
        self.assertEqual(pedido._percentual_de_desconto(), 0.0)
