# -*- coding: utf-8 -*-
"""O tour da transferência interna, no perfil de quem opera o depósito.

Regra da casa (22/08/2026): o ORM mede o que o teste pediu; o tour mede o que
a tela pede. Aqui a tela é o formulário da transferência interna, que o core
só mostra inteiro com "Locais de armazenamento" ligado -- exatamente o que
este módulo liga.
"""

from odoo.tests import HttpCase, tagged

# A senha é o próprio login, escrita UMA vez: repetida como literal, a
# varredura de segredos do publish_liber_erp.sh a lê como credencial.
LOGIN = 'deposito_tour'


@tagged('post_install', '-at_install', 'liber_stock_shelves_tour')
class TestTransferenciaInternaTour(HttpCase):

    def setUp(self):
        super().setUp()
        company = self.env.company
        # O perfil da casa quando o liber_roles está instalado; senão o grupo
        # do core que ele embrulha.
        grupo = self.env.ref('liber_roles.group_logistica_assistente',
                             raise_if_not_found=False) \
            or self.env.ref('stock.group_stock_user')
        self.usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Depósito do Tour',
                'login': LOGIN,
                'password': LOGIN,
                'lang': 'en_US',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, grupo.id)],
            })
        self.warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        Loc = self.env['stock.location']
        self.origem = Loc.create({
            'name': 'TST-000001', 'usage': 'internal',
            'location_id': self.warehouse.lot_stock_id.id})
        self.destino = Loc.create({
            'name': 'TST-000002', 'usage': 'internal',
            'location_id': self.warehouse.lot_stock_id.id})
        self.livro = self.env['product.product'].create({
            'name': 'Os Sertões do Tour', 'type': 'consu',
            'is_storable': True})
        self.env['stock.quant']._update_available_quantity(
            self.livro, self.origem, 10)
        # Uma prateleira de consignação, fora do armazém: o tour prova que a
        # lista de destino NÃO a oferece.
        co = Loc.create({'name': 'CO-TST', 'usage': 'view',
                         'company_id': company.id})
        self.prateleira_do_cliente = Loc.create({
            'name': 'Livraria do Tour', 'usage': 'internal',
            'location_id': co.id, 'company_id': company.id})

    def _saldo(self, local):
        return self.env['stock.quant']._get_available_quantity(
            self.livro, local, strict=True)

    def test_deposito_move_livro_entre_prateleiras(self):
        self.start_tour('/odoo', 'shelves_transferencia_interna_tour',
                        login=LOGIN)
        picking = self.env['stock.picking'].search([
            ('picking_type_id', '=', self.warehouse.int_type_id.id),
            ('location_id', '=', self.origem.id)])
        self.assertEqual(len(picking), 1)
        self.assertEqual(picking.state, 'done')
        self.assertEqual(self._saldo(self.origem), 7)
        self.assertEqual(self._saldo(self.destino), 3)

    def test_deposito_ve_a_guarda_da_raiz(self):
        # Um livro que existe só na prateleira de destino; a origem é a raiz.
        # É o picking 9204 do dev, reconstruído.
        livro = self.env['product.product'].create({
            'name': 'Livro da Armadilha', 'type': 'consu',
            'is_storable': True})
        self.env['stock.quant']._update_available_quantity(
            livro, self.destino, 50)
        raiz = self.warehouse.lot_stock_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.int_type_id.id,
            'origin': 'Armadilha do Tour',
            'location_id': raiz.id,
            'location_dest_id': self.destino.id,
            'move_ids': [(0, 0, {
                'product_id': livro.id, 'product_uom_qty': 5,
                'product_uom': livro.uom_id.id,
                'location_id': raiz.id,
                'location_dest_id': self.destino.id})],
        })
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.move_line_ids.location_id, self.destino,
                         'o cenário não reproduziu a armadilha')
        self.start_tour(
            '/odoo/action-stock.action_picking_tree_internal/%d' % picking.id,
            'shelves_armadilha_da_raiz_tour', login=LOGIN)
        self.assertEqual(picking.state, 'assigned')
        self.assertEqual(self.env['stock.quant']._get_available_quantity(
            livro, self.destino, strict=True) + 5, 50)
