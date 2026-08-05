# -*- coding: utf-8 -*-
"""A tradução pura: parse de data, ISBN, netCost. Sem banco, sem rede.

Roda em milissegundos porque não toca em nada. É de propósito: o que erra em
silêncio na integração é sempre isto -- um campo aninhado que mudou de lugar,
uma data com formato inesperado -- e esse tipo de erro merece um teste que
ninguém tenha preguiça de rodar.
"""

from odoo.tests import TransactionCase, tagged

from ..services import mapping
from .common import amazon_item, amazon_order


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonMapping(TransactionCase):

    def test_z_suffix_becomes_naive_utc(self):
        """A Amazon manda 'Z'; o Odoo guarda datetime ingênuo em UTC.

        Gravar um datetime com fuso levanta erro na hora de escrever.
        """
        parsed = mapping.parse_amazon_datetime('2026-07-01T10:00:00Z')
        self.assertIsNone(parsed.tzinfo)
        self.assertEqual(str(parsed), '2026-07-01 10:00:00')

    def test_offset_is_converted_to_utc(self):
        parsed = mapping.parse_amazon_datetime('2026-07-01T10:00:00-03:00')
        self.assertEqual(str(parsed), '2026-07-01 13:00:00')

    def test_garbage_date_is_none_not_an_exception(self):
        """Pedido sem data ainda é pedido. Derrubá-lo perde a venda para
        salvar o calendário."""
        for value in ('', None, False, 'ontem', '2026-13-45T99:99:99Z'):
            self.assertIsNone(mapping.parse_amazon_datetime(value))

    def test_delivery_window_splits_on_the_double_dash(self):
        start, end = mapping.parse_delivery_window(
            '2026-07-10T00:00:00Z--2026-07-20T00:00:00Z')
        self.assertEqual(str(start), '2026-07-10 00:00:00')
        self.assertEqual(str(end), '2026-07-20 00:00:00')

    def test_malformed_window_is_absence_not_error(self):
        for value in ('', None, '2026-07-10T00:00:00Z', 'qualquer coisa'):
            self.assertEqual(mapping.parse_delivery_window(value), (None, None))

    def test_isbn_comes_from_the_vendor_identifier_not_the_asin(self):
        """O ASIN é código interno da Amazon e não existe no nosso cadastro."""
        line = mapping.map_item(amazon_item('1', '9786551590016', asin='B00TEST'))
        self.assertEqual(line['isbn'], '9786551590016')
        self.assertEqual(line['asin'], 'B00TEST')

    def test_isbn_is_normalised(self):
        line = mapping.map_item(amazon_item('1', '978-65-5159-001-6'))
        self.assertEqual(line['isbn'], '9786551590016')

    def test_unknown_state_is_flagged_not_rejected(self):
        mapped = mapping.map_purchase_order(
            amazon_order('X', [], state='Rejected'))
        self.assertEqual(mapped['amazon_state'], 'Rejected')
        self.assertFalse(mapped['state_known'])
        self.assertFalse(mapped['is_open'])

    def test_closed_is_known_but_not_open(self):
        mapped = mapping.map_purchase_order(amazon_order('X', [], state='Closed'))
        self.assertTrue(mapped['state_known'])
        self.assertFalse(mapped['is_open'])

    def test_report_counts_what_will_hurt(self):
        report = mapping.import_report([
            amazon_order('A', [
                amazon_item('1', '9786551590016', qty=10, net_cost='45.50'),
                amazon_item('2', None, qty=5),
            ]),
            amazon_order('B', [
                amazon_item('1', '9786551590016', qty=2, net_cost='45.50'),
            ], state='Weird'),
        ])
        self.assertEqual(report['orders'], 2)
        self.assertEqual(report['lines'], 3)
        self.assertEqual(report['isbns'], ['9786551590016'])
        self.assertEqual(report['lines_without_isbn'], 1)
        self.assertEqual(report['unknown_states'], ['Weird'])
        # 10 × 45,50 + 5 × 45,50 + 2 × 45,50 = 773,50. A linha sem ISBN entra
        # no total: ela não casa com produto, mas a Amazon vai pagar por ela.
        self.assertAlmostEqual(report['total'], 773.50, places=2)

    def test_empty_payload(self):
        report = mapping.import_report([])
        self.assertEqual(report['orders'], 0)
        self.assertEqual(report['total'], 0)
