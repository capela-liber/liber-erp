# -*- coding: utf-8 -*-
"""Os tours do inventário físico, nos dois perfis que o operam.

Regra da casa (22/08/2026): o ORM mede o que o teste pediu; o tour mede o que
a tela pede. Aqui a tela é o Inventário físico, e o que se prova é que o
assistente conta sem ver "Aplicar", e que o gerente vê e aplica.
"""

from odoo import fields
from odoo.tests import HttpCase, tagged

# A senha é o próprio login, escrita UMA vez: repetida como literal, a
# varredura de segredos do publish_liber_erp.sh a lê como credencial.
LOGIN_ASSISTENTE = 'contagem_tour'
LOGIN_GERENTE = 'gerente_contagem_tour'


@tagged('post_install', '-at_install', 'liber_stock_count_tour')
class TestInventarioTour(HttpCase):

    def setUp(self):
        super().setUp()
        company = self.env.company
        Users = self.env['res.users'].with_context(no_reset_password=True)

        def _grupo(casa, core):
            # O perfil da casa quando o liber_roles está instalado; senão o
            # grupo do core que ele embrulha.
            return self.env.ref(casa, raise_if_not_found=False) \
                or self.env.ref(core)

        def _usuario(nome, login, grupo):
            return Users.create({
                'name': nome, 'login': login, 'password': login,
                'lang': 'en_US',
                'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, grupo.id)],
            })

        self.assistente = _usuario(
            'Depósito do Tour', LOGIN_ASSISTENTE,
            _grupo('liber_roles.group_logistica_assistente',
                   'stock.group_stock_user'))
        self.gerente = _usuario(
            'Gerente do Tour', LOGIN_GERENTE,
            _grupo('liber_roles.group_logistica_gerente',
                   'stock.group_stock_manager'))
        self.warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        self.prateleira = self.env['stock.location'].create({
            'name': 'TST-000007', 'usage': 'internal',
            'location_id': self.warehouse.lot_stock_id.id})
        self.livro = self.env['product.product'].create({
            'name': 'Livro da Contagem', 'type': 'consu',
            'is_storable': True})
        Quant = self.env['stock.quant']
        Quant._update_available_quantity(self.livro, self.prateleira, 10)
        self.quant = Quant._gather(self.livro, self.prateleira, strict=True)
        # O gerente pediu a contagem ao assistente: é o que "Solicitar uma
        # contagem" grava, e o que põe a linha em "Minhas contagens".
        self.quant.with_context(inventory_mode=True).write({
            'user_id': self.assistente.id,
            'inventory_date': fields.Date.context_today(self.env.user)})

    def test_assistente_conta_e_nao_aplica(self):
        self.start_tour('/odoo', 'count_assistente_tour',
                        login=LOGIN_ASSISTENTE)
        self.quant.invalidate_recordset()
        self.assertEqual(self.quant.inventory_quantity, 7)
        self.assertTrue(self.quant.inventory_quantity_set)
        self.assertEqual(self.quant.user_id, self.assistente)
        self.assertEqual(self.quant.quantity, 10, 'contar não é aplicar')

    def test_gerente_aplica(self):
        self.quant.with_user(self.assistente).with_context(
            inventory_mode=True).write({'inventory_quantity': 7})
        self.start_tour('/odoo', 'count_gerente_tour', login=LOGIN_GERENTE)
        self.quant.invalidate_recordset()
        self.assertEqual(self.quant.quantity, 7)
        self.assertFalse(self.quant.inventory_quantity_set)
        ajuste = self.env['stock.move.line'].search([
            ('product_id', '=', self.livro.id), ('state', '=', 'done'),
            ('location_dest_id.usage', '=', 'inventory')])
        self.assertEqual(len(ajuste), 1)
        self.assertEqual(ajuste.quantity, 3)
