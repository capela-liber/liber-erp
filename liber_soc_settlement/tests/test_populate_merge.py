# -*- coding: utf-8 -*-
"""O botão Mapa preenche MESCLANDO — apagar o que o operador digitou era
perder a importação do atendimento (10/08/2026)."""
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestPopulateMerge(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria Merge', 'email': 'merge@livraria.test',
            'allow_consignment': True})
        cls.agreement = cls.env['consignment.agreement'].create(
            {'partner_id': cls.partner.id})
        cls.agreement.action_activate()
        Product = cls.env['product.product']
        make = lambda n: Product.create({
            'name': n, 'type': 'consu', 'is_storable': True,
            'sale_ok': True, 'list_price': 40.0})
        cls.typed_off_shelf = make('Digitado fora da prateleira')
        cls.on_shelf = make('Na prateleira')
        cls.untouched_off_shelf = make('Intocado fora da prateleira')
        cls.env['stock.quant'].create({
            'location_id': cls.agreement.location_id.id,
            'product_id': cls.on_shelf.id, 'quantity': 5})
        cls.settlement = cls.env['consignment.settlement'].create(
            {'partner_id': cls.partner.id})
        Line = cls.env['consignment.settlement.line']
        cls.line_typed = Line.create({
            'settlement_id': cls.settlement.id,
            'product_id': cls.typed_off_shelf.id, 'qty_reported': 3})
        cls.line_untouched = Line.create({
            'settlement_id': cls.settlement.id,
            'product_id': cls.untouched_off_shelf.id})

    def test_map_merges_instead_of_wiping(self):
        self.settlement.action_populate_from_shelf()
        products = self.settlement.line_ids.mapped('product_id')
        # a digitada sobreviveu com a quantidade
        self.assertIn(self.typed_off_shelf, products)
        self.assertEqual(self.line_typed.qty_reported, 3,
                         "o Mapa não pode apagar o acerto digitado")
        # a da prateleira entrou
        self.assertIn(self.on_shelf, products)
        # a intocada fora da prateleira saiu
        self.assertNotIn(self.untouched_off_shelf, products)

    def test_map_does_not_duplicate_existing_shelf_line(self):
        self.settlement.action_populate_from_shelf()
        self.settlement.action_populate_from_shelf()  # segunda vez
        lines = self.settlement.line_ids.filtered(
            lambda l: l.product_id == self.on_shelf)
        self.assertEqual(len(lines), 1, "repetir o Mapa não duplica linha")


@tagged('post_install', '-at_install')
class TestRunNoshelf(common.TransactionCase):
    """Acertar livro que a prateleira não tem: alerta, roda sem eles, e
    deixa Atividade de correção de estoque (pedido de 10/08/2026)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria Fantasma', 'email': 'ghost@livraria.test',
            'allow_consignment': True})
        cls.agreement = cls.env['consignment.agreement'].create(
            {'partner_id': cls.partner.id})
        cls.agreement.action_activate()
        Product = cls.env['product.product']
        make = lambda n: Product.create({
            'name': n, 'type': 'consu', 'is_storable': True,
            'sale_ok': True, 'list_price': 40.0})
        cls.real = make('Está na prateleira')
        cls.ghost = make('Fantasma no acerto')
        cls.env['stock.quant'].create({
            'location_id': cls.agreement.location_id.id,
            'product_id': cls.real.id, 'quantity': 5})
        cls.settlement = cls.env['consignment.settlement'].create(
            {'partner_id': cls.partner.id})
        Line = cls.env['consignment.settlement.line']
        cls.line_real = Line.create({
            'settlement_id': cls.settlement.id,
            'product_id': cls.real.id, 'qty_reported': 2})
        cls.line_ghost = Line.create({
            'settlement_id': cls.settlement.id,
            'product_id': cls.ghost.id, 'qty_reported': 3})

    def test_run_offers_wizard_and_stays_draft(self):
        action = self.settlement.action_run()
        self.assertEqual(action.get('res_model'),
                         'consignment.run.noshelf.wizard')
        self.assertEqual(self.settlement.state, 'draft',
                         "nada roda antes da decisão")

    def test_wizard_drops_ghost_runs_rest_and_nags(self):
        action = self.settlement.action_run()
        wizard = self.env['consignment.run.noshelf.wizard'].browse(
            action['res_id'])
        wizard.action_remove_and_run()
        self.assertNotIn(self.ghost,
                         self.settlement.line_ids.mapped('product_id'),
                         "o fantasma saiu da CO")
        self.assertEqual(self.settlement.state, 'confirmed',
                         "o resto rodou")
        activity = self.settlement.activity_ids
        self.assertTrue(activity, "ficou a Atividade de correção")
        self.assertIn('Fantasma no acerto', activity.note or '',
                      "a Atividade diz QUAL título saiu")

    def test_ghost_with_replenish_keeps_line(self):
        """Linha com reposição legítima não some — só o acerto zera."""
        self.line_ghost.qty_replenish = 4
        # precisa de estoque em mãos para a reposição passar no overstock
        wh = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        self.env['stock.quant'].create({
            'location_id': wh.lot_stock_id.id,
            'product_id': self.ghost.id, 'quantity': 10})
        action = self.settlement.action_run()
        wizard = self.env['consignment.run.noshelf.wizard'].browse(
            action['res_id'])
        wizard.action_remove_and_run()
        self.assertIn(self.ghost,
                      self.settlement.line_ids.mapped('product_id'))
        self.assertEqual(self.line_ghost.qty_reported, 0)
        self.assertEqual(self.line_ghost.qty_replenish, 4)
