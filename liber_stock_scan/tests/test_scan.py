# -*- coding: utf-8 -*-
"""O serviço da bipagem, no ORM: o que cada código é, e a transferência."""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_stock_scan')
class TestShelfScan(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.raiz = cls.warehouse.lot_stock_id
        Loc = cls.env['stock.location']
        cls.a = Loc.create({'name': 'SCN-000001', 'usage': 'internal',
                            'location_id': cls.raiz.id})
        cls.b = Loc.create({'name': 'SCN-000002', 'usage': 'internal',
                            'location_id': cls.raiz.id})
        co = Loc.create({'name': 'CO-SCN', 'usage': 'view',
                         'company_id': cls.company.id})
        cls.cliente = Loc.create({'name': 'Livraria da Bipagem',
                                  'usage': 'internal', 'location_id': co.id,
                                  'company_id': cls.company.id})
        Prod = cls.env['product.product']
        cls.livro = Prod.create({'name': 'Livro Bipado', 'type': 'consu',
                                 'is_storable': True,
                                 'barcode': '9780000000031'})
        cls.outro = Prod.create({'name': 'Livro de Outra Prateleira',
                                 'type': 'consu', 'is_storable': True,
                                 'barcode': '9780000000048'})
        Quant = cls.env['stock.quant']
        Quant._update_available_quantity(cls.livro, cls.a, 10)
        Quant._update_available_quantity(cls.outro, cls.b, 4)
        cls.Scan = cls.env['liber.shelf.scan']

    def _saldo(self, produto, local):
        quants = self.env['stock.quant'].search([
            ('product_id', '=', produto.id), ('location_id', '=', local.id)])
        return sum(quants.mapped('quantity'))

    # -- etiquetas ------------------------------------------------------------

    def test_prateleira_nasce_com_codigo_de_barras(self):
        self.assertEqual(self.a.barcode, 'SCN-000001')
        self.assertTrue(self.a._liber_is_shelf())
        self.assertFalse(self.raiz._liber_is_shelf())
        self.assertFalse(self.cliente._liber_is_shelf(),
                         'a prateleira do cliente não é do armazém')

    def test_gancho_e_idempotente(self):
        self.a.barcode = False
        feitas = self.env['stock.location']._liber_etiquetar_prateleiras()
        self.assertIn(self.a, feitas)
        self.assertEqual(self.a.barcode, 'SCN-000001')
        self.assertFalse(self.env['stock.location']._liber_etiquetar_prateleiras()
                         & self.a)

    # -- scan --------------------------------------------------------------------

    def test_scan_prateleira(self):
        r = self.Scan.scan('SCN-000001')
        self.assertEqual(r['kind'], 'location')
        self.assertEqual(r['id'], self.a.id)
        # Pelo nome completo também: a etiqueta antiga do core.
        self.assertEqual(self.Scan.scan(self.a.complete_name)['id'], self.a.id)

    def test_scan_raiz_e_cliente_sao_recusados(self):
        self.assertEqual(self.Scan.scan(self.raiz.complete_name)['kind'], 'error')
        self.assertEqual(self.Scan.scan('Livraria da Bipagem')['kind'], 'error')

    def test_scan_livro_na_prateleira(self):
        r = self.Scan.scan('9780000000031', self.a.id)
        self.assertEqual(r['kind'], 'product')
        self.assertEqual(r['id'], self.livro.id)
        self.assertEqual(r['on_hand'], 10)

    def test_scan_livro_fora_da_prateleira_diz_onde_esta(self):
        r = self.Scan.scan('9780000000048', self.a.id)
        self.assertEqual(r['kind'], 'error')
        self.assertIn('SCN-000002 (4)', r['message'])

    def test_scan_codigo_desconhecido(self):
        r = self.Scan.scan('0000000000000', self.a.id)
        self.assertEqual(r['kind'], 'error')
        self.assertIn('0000000000000', r['message'])

    # -- transfer -----------------------------------------------------------------

    def test_transferencia_valida_na_hora(self):
        r = self.Scan.transfer(self.a.id, self.b.id,
                               [{'product_id': self.livro.id, 'qty': 1},
                                {'product_id': self.livro.id, 'qty': 2}])
        picking = self.env['stock.picking'].browse(r['picking_id'])
        self.assertEqual(picking.state, 'done')
        self.assertEqual(picking.picking_type_id, self.warehouse.int_type_id)
        self.assertEqual(r['qty'], 3)
        self.assertEqual(self._saldo(self.livro, self.a), 7)
        self.assertEqual(self._saldo(self.livro, self.b), 3)
        self.assertEqual(picking.move_line_ids.location_id, self.a)
        self.assertEqual(picking.move_line_ids.location_dest_id, self.b)

    def test_transferencia_sem_estoque_suficiente_falha_inteira(self):
        with self.assertRaises(UserError) as cm:
            self.Scan.transfer(self.a.id, self.b.id,
                               [{'product_id': self.livro.id, 'qty': 11}])
        self.assertIn('10 of 11', str(cm.exception))
        self.assertEqual(self._saldo(self.livro, self.a), 10)
        self.assertFalse(self.env['stock.picking'].search(
            [('origin', '=', 'Scan'), ('state', '=', 'done')]))

    def test_transferencia_para_prateleira_do_cliente_e_recusada(self):
        with self.assertRaises(UserError):
            self.Scan.transfer(self.a.id, self.cliente.id,
                               [{'product_id': self.livro.id, 'qty': 1}])

    def test_transferencia_mesma_prateleira_e_recusada(self):
        with self.assertRaises(UserError):
            self.Scan.transfer(self.a.id, self.a.id,
                               [{'product_id': self.livro.id, 'qty': 1}])

    def test_transferencia_sem_livros_e_recusada(self):
        with self.assertRaises(UserError):
            self.Scan.transfer(self.a.id, self.b.id, [])
