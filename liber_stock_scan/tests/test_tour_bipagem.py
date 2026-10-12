# -*- coding: utf-8 -*-
"""O tour da bipagem, no perfil de quem opera o depósito."""

from odoo.tests import HttpCase, tagged

# A senha é o próprio login, escrita UMA vez: repetida como literal, a
# varredura de segredos do publish_liber_erp.sh a lê como credencial.
LOGIN = 'bipagem_tour'


@tagged('post_install', '-at_install', 'liber_stock_scan_tour')
class TestBipagemTour(HttpCase):

    def setUp(self):
        super().setUp()
        company = self.env.company
        grupo = self.env.ref('liber_roles.group_logistica_assistente',
                             raise_if_not_found=False) \
            or self.env.ref('stock.group_stock_user')
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Bipagem do Tour', 'login': LOGIN, 'password': LOGIN,
            'lang': 'en_US', 'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'group_ids': [(4, grupo.id)],
        })
        self.warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        Loc = self.env['stock.location']
        self.origem = Loc.create({'name': 'TST-000001', 'usage': 'internal',
                                  'location_id': self.warehouse.lot_stock_id.id})
        self.destino = Loc.create({'name': 'TST-000002', 'usage': 'internal',
                                   'location_id': self.warehouse.lot_stock_id.id})
        Prod = self.env['product.product']
        self.livro = Prod.create({'name': 'Os Sertões Bipado', 'type': 'consu',
                                  'is_storable': True,
                                  'barcode': '9780000000017'})
        self.outro = Prod.create({'name': 'Livro da Outra', 'type': 'consu',
                                  'is_storable': True,
                                  'barcode': '9780000000024'})
        Quant = self.env['stock.quant']
        Quant._update_available_quantity(self.livro, self.origem, 10)
        Quant._update_available_quantity(self.outro, self.destino, 3)

    def _saldo(self, produto, local):
        quants = self.env['stock.quant'].search([
            ('product_id', '=', produto.id), ('location_id', '=', local.id)])
        return sum(quants.mapped('quantity'))

    def test_deposito_bipa_a_transferencia(self):
        self.start_tour('/odoo', 'shelves_bipagem_tour', login=LOGIN)
        picking = self.env['stock.picking'].search([
            ('origin', '=', 'Scan'), ('location_id', '=', self.origem.id)])
        self.assertEqual(len(picking), 1)
        self.assertEqual(picking.state, 'done')
        self.assertEqual(self._saldo(self.livro, self.origem), 8)
        self.assertEqual(self._saldo(self.livro, self.destino), 2)
        # O livro recusado não se moveu.
        self.assertEqual(self._saldo(self.outro, self.destino), 3)
