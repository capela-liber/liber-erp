# -*- coding: utf-8 -*-
"""A importação: o que grava, o que reescreve e o que se recusa a reescrever."""

from odoo.tests import tagged

from .common import AmazonVendorCase, amazon_item, amazon_order


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonSync(AmazonVendorCase):

    # ------------------------------------------------------- caminho feliz

    def test_import_creates_order_and_lines(self):
        result = self._sync([amazon_order('BR-0001', [
            amazon_item('1', '9786551590016', qty=30, net_cost='45.50'),
            amazon_item('2', '9786551590085', qty=12, net_cost='40.00'),
        ])])

        self.assertEqual(result['created'], 1)
        order = self._order('BR-0001')
        self.assertEqual(order.amazon_state, 'Acknowledged')
        self.assertTrue(order.state_known)
        self.assertTrue(order.is_open)
        self.assertEqual(order.line_count, 2)
        self.assertEqual(order.state, 'imported')
        self.assertFalse(order.sale_order_id)
        # 30 × 45,50 + 12 × 40,00
        self.assertAlmostEqual(order.amount_total, 1845.0, places=2)

    def test_isbn_matches_product_by_barcode(self):
        self._sync([amazon_order('BR-0002', [
            amazon_item('1', '9786551590016'),
        ])])
        line = self._order('BR-0002').line_ids
        self.assertEqual(line.product_id, self.book_a)
        self.assertTrue(line.matched)

    def test_hyphenated_barcode_still_matches(self):
        """O catálogo real tem barcode com hífen. A Amazon manda sem.

        Sem normalizar dos dois lados, o título cadastrado apareceria como
        ausente -- e o relatório mandaria cadastrar o que já existe.
        """
        self._sync([amazon_order('BR-0003', [
            amazon_item('1', '9786551590085'),
        ])])
        self.assertEqual(self._order('BR-0003').line_ids.product_id, self.book_b)

    def test_delivery_window_is_split(self):
        self._sync([amazon_order('BR-0004', [amazon_item('1', '9786551590016')])])
        order = self._order('BR-0004')
        self.assertEqual(str(order.delivery_start), '2026-07-10 00:00:00')
        self.assertEqual(str(order.delivery_end), '2026-07-20 00:00:00')

    def test_net_cost_is_the_price_not_list_price(self):
        """netCost é o que a Amazon paga; listPrice é a etiqueta dela.

        Trocar os dois infla a receita do pedido inteiro e só aparece no
        fechamento do mês.
        """
        self._sync([amazon_order('BR-0005', [
            amazon_item('1', '9786551590016', qty=1,
                        net_cost='45.50', list_price='89.90'),
        ])])
        line = self._order('BR-0005').line_ids
        self.assertAlmostEqual(line.price_unit, 45.50, places=2)
        self.assertAlmostEqual(line.list_price, 89.90, places=2)

    # ----------------------------------------------------------- reimportar

    def test_reimport_does_not_duplicate(self):
        """A janela de leitura recua de propósito: sobreposição é a regra."""
        payload = [amazon_order('BR-0010', [amazon_item('1', '9786551590016')])]
        first = self._sync(payload)
        second = self._sync(payload)

        self.assertEqual(first['created'], 1)
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['updated'], 1)
        self.assertEqual(len(self._order('BR-0010')), 1)
        self.assertEqual(self._order('BR-0010').line_count, 1)

    def test_reimport_updates_state(self):
        """Amazon muda o estado depois de criado; o espelho tem de acompanhar."""
        self._sync([amazon_order('BR-0011', [amazon_item('1', '9786551590016')],
                                 state='New')])
        self.assertEqual(self._order('BR-0011').amazon_state, 'New')

        self._sync([amazon_order('BR-0011', [amazon_item('1', '9786551590016')],
                                 state='Closed')])
        order = self._order('BR-0011')
        self.assertEqual(order.amazon_state, 'Closed')
        self.assertFalse(order.is_open)

    def test_manual_product_survives_reimport(self):
        """Correção humana não pode ser desfeita pela próxima leitura."""
        self._sync([amazon_order('BR-0012', [
            amazon_item('1', '9788500000009'),  # fora do cadastro
        ])])
        line = self._order('BR-0012').line_ids
        self.assertFalse(line.product_id)

        line.product_id = self.book_a          # alguém resolve à mão
        self.assertTrue(line.product_locked)

        self._sync([amazon_order('BR-0012', [amazon_item('1', '9788500000009')])])
        self.assertEqual(self._order('BR-0012').line_ids.product_id, self.book_a)

    # -------------------------------------------------------------- avisos

    def test_unknown_state_is_imported_not_rejected(self):
        """O agregador anterior levantava exceção aqui e perdia o pedido.

        Estado novo na Amazon é notícia, não motivo para descartar uma venda.
        """
        self._sync([amazon_order('BR-0020', [amazon_item('1', '9786551590016')],
                                 state='Rejected')])
        order = self._order('BR-0020')
        self.assertTrue(order, "o pedido tem de existir mesmo com estado novo")
        self.assertEqual(order.amazon_state, 'Rejected')
        self.assertFalse(order.state_known)
        self.assertFalse(order.is_open)

    def test_unmatched_isbn_is_counted_not_fatal(self):
        self._sync([amazon_order('BR-0021', [
            amazon_item('1', '9786551590016'),
            amazon_item('2', '9788500000009'),
        ])])
        order = self._order('BR-0021')
        self.assertEqual(order.line_count, 2)
        self.assertEqual(order.unmatched_count, 1)

    # ---------------------------------------------------------- divergência

    def test_change_after_quotation_is_flagged_not_applied(self):
        """
        A Amazon aceita pedido parcial, e a quantidade confirmada raramente é
        a pedida. Depois que existe cotação, quantidade que muda é problema de
        alguém -- e o módulo avisa em vez de reescrever um documento que uma
        pessoa fez.
        """
        self._sync([amazon_order('BR-0030', [
            amazon_item('1', '9786551590016', qty=100),
        ])])
        order = self._order('BR-0030')
        order.action_create_quotation()
        self.assertTrue(order.sale_order_id)

        self._sync([amazon_order('BR-0030', [
            amazon_item('1', '9786551590016', qty=60),
        ], state='Closed')])

        order = self._order('BR-0030')
        self.assertTrue(order.has_divergence)
        self.assertIn('100', order.divergence_note)
        self.assertIn('60', order.divergence_note)
        # A cotação continua intacta: ninguém reescreveu por baixo.
        self.assertAlmostEqual(
            order.sale_order_id.order_line.product_uom_qty, 100, places=2)

    def test_change_before_quotation_is_not_a_divergence(self):
        """Sem cotação, mudança é só notícia: o espelho se atualiza e pronto."""
        self._sync([amazon_order('BR-0031', [
            amazon_item('1', '9786551590016', qty=100)])])
        self._sync([amazon_order('BR-0031', [
            amazon_item('1', '9786551590016', qty=60)])])

        order = self._order('BR-0031')
        self.assertFalse(order.has_divergence)
        self.assertAlmostEqual(order.line_ids.quantity, 60, places=2)

    def test_acknowledging_divergence_clears_the_flag(self):
        self._sync([amazon_order('BR-0032', [
            amazon_item('1', '9786551590016', qty=100)])])
        order = self._order('BR-0032')
        order.action_create_quotation()
        self._sync([amazon_order('BR-0032', [
            amazon_item('1', '9786551590016', qty=60)])])

        order = self._order('BR-0032')
        self.assertTrue(order.has_divergence)
        order.action_clear_divergence()
        self.assertFalse(order.has_divergence)

    # ----------------------------------------------------------- edge cases

    def test_order_without_delivery_window(self):
        """Pedido sem janela ainda é pedido. Não pode derrubar a importação."""
        self._sync([amazon_order('BR-0040', [amazon_item('1', '9786551590016')],
                                 window=None)])
        order = self._order('BR-0040')
        self.assertTrue(order)
        self.assertFalse(order.delivery_start)

    def test_line_without_price(self):
        self._sync([amazon_order('BR-0041', [
            amazon_item('1', '9786551590016', qty=5, net_cost=None),
        ])])
        order = self._order('BR-0041')
        self.assertAlmostEqual(order.amount_total, 0.0, places=2)

    def test_order_without_items(self):
        self._sync([amazon_order('BR-0042', [])])
        order = self._order('BR-0042')
        self.assertTrue(order)
        self.assertEqual(order.line_count, 0)

    def test_order_without_number_is_skipped(self):
        """Sem PO number não há chave: gravar criaria um registro anônimo
        que a próxima leitura duplicaria."""
        result = self._sync([amazon_order('', [amazon_item('1', '9786551590016')])])
        self.assertEqual(result['created'], 0)
