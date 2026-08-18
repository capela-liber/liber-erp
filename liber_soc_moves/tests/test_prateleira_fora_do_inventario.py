# -*- coding: utf-8 -*-
"""O fluxo interno de prateleira perde o cartão e mantém o movimento.

Ele abriu a Visão geral do inventário e viu dois cartões de consignação lado a
lado -- "Remessa de Consignação" e "Entrega de Consignação" -- e perguntou qual
era o abstrato. Era o primeiro: COM/MOV, armazém -> prateleira do cliente. O
segundo, COM/OUT, é a remessa física do Pedido C, a que o armazém trabalha.

Pior: o COM/MOV não é mais alcançável pela tela (a `consignment.move` virou o
CR, com domínio de retorno e sem criar), então o cartão pedia um trabalho que
ninguém pode criar.

O que estes testes prendem é que arquivar compra o cartão e não custa mais
nada: a prateleira continua sendo debitada, por uma transferência que continua
tendo nome e número.
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPrateleiraForaDoInventario(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': 'Livro da Prateleira', 'type': 'consu', 'is_storable': True,
            'list_price': 40.0})

    def _agreement(self):
        partner = self.env['res.partner'].create({
            'name': 'Livraria da Prateleira', 'is_company': True})
        agreement = self.env['consignment.agreement'].create({
            'partner_id': partner.id, 'company_id': self.company.id,
            'date_start': fields.Date.today() - timedelta(days=1),
        })
        agreement.action_activate()
        return agreement

    def _stock_the_warehouse(self, qty):
        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.product.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'inventory_quantity': qty,
        }).action_apply_inventory()

    # ------------------------------------------------------------------

    def test_operation_type_is_born_off_the_overview(self):
        """A Visão geral lista o que uma busca padrão devolve. Arquivado é
        exatamente como um registro fica fora de uma."""
        operation_type = self.company._get_consignment_shipment_operation_type()

        self.assertTrue(operation_type,
                        "o fluxo de prateleira ainda precisa do tipo próprio")
        self.assertFalse(
            operation_type.active,
            "o movimento interno de prateleira não é trabalho de armazém e "
            "não pode puxar cartão")
        self.assertNotIn(
            operation_type, self.env['stock.picking.type'].search([]),
            "a busca com active_test é o que o kanban da Visão geral roda")

    def test_the_delivery_type_keeps_its_card(self):
        """O outro lado da regra: a remessa de verdade continua na tela.

        Arquivar o abstrato só resolve a confusão se o COM/OUT -- a saída do
        Pedido C, o trabalho que o armazém realmente faz -- continuar visível."""
        delivery = self.company._get_consignment_delivery_operation_type()

        self.assertTrue(delivery.active,
                        "a remessa do Pedido C é trabalho de armazém")
        self.assertIn(delivery, self.env['stock.picking.type'].search([]))

    def test_the_type_is_created_once_and_reused(self):
        """Arquivar não pode fazer o getter achar que sumiu e cunhar um novo a
        cada remessa."""
        first = self.company._get_consignment_shipment_operation_type()
        second = self.company._get_consignment_shipment_operation_type()

        self.assertEqual(first, second)
        self.assertEqual(
            self.env['stock.picking.type'].with_context(
                active_test=False).search_count(
                    [('sequence_code', '=', 'COM/MOV'),
                     ('company_id', '=', self.company.id)]),
            1, "um COM/MOV por empresa, quantas vezes se chame")

    def test_the_shelf_shipment_still_happens(self):
        """O ponto todo da opção A: o cartão vai, o movimento fica."""
        agreement = self._agreement()
        self._stock_the_warehouse(15)
        shipment = self.env['consignment.move'].create({
            'partner_id': agreement.partner_id.id,
            'move_kind': 'shipment',
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 6,
                'product_uom': self.product.uom_id.id,
            })],
        })
        shipment.action_confirm()
        shipment.action_release()

        picking = shipment.picking_id
        self.assertTrue(picking, "a remessa de prateleira ainda cria transferência")
        self.assertFalse(picking.picking_type_id.active,
                         "e a cria no tipo arquivado")
        self.assertTrue(picking.name.startswith('COM/MOV/'),
                        "a numeração própria continua: %r" % picking.name)

        picking.move_ids.picked = True
        picking.button_validate()

        on_shelf = sum(self.env['stock.quant'].search([
            ('location_id', '=', agreement.location_id.id),
            ('product_id', '=', self.product.id)]).mapped('quantity'))
        self.assertEqual(on_shelf, 6,
                         "o que foi remetido tem que estar na prateleira")

    def test_migration_archives_an_already_active_type(self):
        """A base que já rodou uma remessa carrega um tipo ativo -- é ele que
        desenha o cartão. A migração tem que alcançá-lo, e rodar duas vezes não
        pode doer."""
        operation_type = self.company._get_consignment_shipment_operation_type()
        operation_type.sudo().active = True   # o estado das bases antigas
        self.env.flush_all()

        migration = self._load_migration()
        migration.migrate(self.env.cr, '19.0.2.6.0')
        self.env.invalidate_all()
        self.assertFalse(operation_type.active)

        migration.migrate(self.env.cr, '19.0.2.6.0')
        self.env.invalidate_all()
        self.assertFalse(operation_type.active, "reexecutar não pode doer")

    def _load_migration(self):
        import importlib.util
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'migrations', '19.0.2.7.0', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('soc_moves_270', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
