# -*- coding: utf-8 -*-
"""A guarda da armadilha da raiz, no ORM.

O caso real (picking 9204 do dev, 08/10/2026): origem = raiz do armazém,
destino = prateleira, e o livro só existe NA prateleira de destino. A reserva
desce a árvore, separa da própria prateleira de destino, e a linha fica dela
para ela mesma. O teste de peça 1 nunca exercitava isso: tinha a prateleira
folha na origem.
"""

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_stock_shelves')
class TestGuardaDaRaiz(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.raiz = cls.warehouse.lot_stock_id
        Loc = cls.env['stock.location']
        cls.prateleira = Loc.create({
            'name': 'TST-000043', 'usage': 'internal',
            'location_id': cls.raiz.id})
        cls.outra = Loc.create({
            'name': 'TST-000044', 'usage': 'internal',
            'location_id': cls.raiz.id})
        cls.livro = cls.env['product.product'].create({
            'name': 'Livro da Raiz', 'type': 'consu', 'is_storable': True})
        # Só na prateleira: a raiz não tem nenhum.
        cls.env['stock.quant']._update_available_quantity(
            cls.livro, cls.prateleira, 329)

    def _interna(self, origem, destino, qty=25):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.int_type_id.id,
            'location_id': origem.id,
            'location_dest_id': destino.id,
            'move_ids': [(0, 0, {
                'product_id': self.livro.id,
                'product_uom_qty': qty,
                'product_uom': self.livro.uom_id.id,
                'location_id': origem.id,
                'location_dest_id': destino.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _saldo(self, local, livro=None):
        """O que há na prateleira, reservado ou não."""
        quants = self.env['stock.quant'].search([
            ('product_id', '=', (livro or self.livro).id),
            ('location_id', '=', local.id)])
        return sum(quants.mapped('quantity'))

    def test_raiz_na_origem_reserva_da_prateleira_de_destino(self):
        """O mecanismo do core, documentado: é isso que a guarda cerca."""
        picking = self._interna(self.raiz, self.prateleira)
        self.assertEqual(picking.state, 'assigned',
                         'o core reservou 25 com zero na raiz: child_of')
        linha = picking.move_line_ids
        self.assertEqual(linha.location_id, self.prateleira)
        self.assertEqual(linha.location_dest_id, self.prateleira)
        self.assertEqual(picking.move_ids.shelf_from, 'TST-000043')

    def test_validar_linha_parada_e_recusado(self):
        picking = self._interna(self.raiz, self.prateleira)
        with self.assertRaises(UserError) as cm:
            picking.button_validate()
        self.assertIn('TST-000043', str(cm.exception))
        self.assertIn('Nothing would move', str(cm.exception))
        self.assertNotEqual(picking.state, 'done')
        self.assertEqual(self._saldo(self.prateleira), 329)

    def test_prateleira_na_origem_passa(self):
        picking = self._interna(self.prateleira, self.outra)
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        self.assertEqual(self._saldo(self.prateleira), 304)
        self.assertEqual(self._saldo(self.outra), 25)

    def test_raiz_na_origem_passa_quando_o_livro_esta_na_raiz(self):
        """Endereçar o resíduo da migração continua possível: com estoque na
        raiz e em nenhuma prateleira, a reserva sai da raiz mesmo."""
        livro = self.env['product.product'].create({
            'name': 'Livro só na Raiz', 'type': 'consu', 'is_storable': True})
        self.env['stock.quant']._update_available_quantity(livro, self.raiz, 24)
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.int_type_id.id,
            'location_id': self.raiz.id,
            'location_dest_id': self.outra.id,
            'move_ids': [(0, 0, {
                'product_id': livro.id, 'product_uom_qty': 10,
                'product_uom': livro.uom_id.id,
                'location_id': self.raiz.id,
                'location_dest_id': self.outra.id})],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        self.assertEqual(self._saldo(self.outra, livro), 10)

    def test_realocar_nao_e_atingido(self):
        """O Realocar cria movimentos sem tipo de operação: a guarda, restrita
        ao tipo interno, não pode alcançá-lo."""
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.livro.id),
            ('location_id', '=', self.prateleira.id)])
        wiz = self.env['stock.quant.relocate'].create({
            'quant_ids': [(6, 0, quant.ids)],
            'dest_location_id': self.outra.id})
        wiz.action_relocate_quants()
        self.assertEqual(self._saldo(self.outra), 329)


@tagged('post_install', '-at_install', 'liber_stock_shelves')
class TestDentroDoArmazem(TestGuardaDaRaiz):
    """A transferência interna não alcança a prateleira de consignação.

    As prateleiras CO/<cliente> são internas e moram fora da árvore do
    armazém; o core as oferecia como destino. Erro grave, nas palavras do
    dono (08/10/2026): transcende o depósito.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.co = cls.env['stock.location'].create({
            'name': 'CO-TST', 'usage': 'view',
            'company_id': cls.company.id})
        cls.prateleira_do_cliente = cls.env['stock.location'].create({
            'name': 'Livraria do Teste', 'usage': 'internal',
            'location_id': cls.co.id, 'company_id': cls.company.id})
        cls.env['stock.quant']._update_available_quantity(
            cls.livro, cls.prateleira_do_cliente, 5)

    def test_prateleira_do_cliente_nao_e_do_armazem(self):
        self.assertFalse(self.prateleira_do_cliente.warehouse_id)
        self.assertEqual(self.prateleira.warehouse_id, self.warehouse)

    def test_cabecalho_recusa_destino_fora_do_armazem(self):
        with self.assertRaises(ValidationError) as cm:
            self._interna(self.prateleira, self.prateleira_do_cliente)
        self.assertIn('Livraria do Teste', str(cm.exception))

    def test_cabecalho_recusa_origem_fora_do_armazem(self):
        with self.assertRaises(ValidationError):
            self._interna(self.prateleira_do_cliente, self.prateleira)

    def test_linha_com_destino_fora_e_recusada_na_validacao(self):
        picking = self._interna(self.prateleira, self.outra)
        # O "Para" de Detalhes aceita qualquer local; a validação não.
        picking.move_line_ids.location_dest_id = self.prateleira_do_cliente
        with self.assertRaises(UserError):
            picking.button_validate()
        self.assertEqual(self._saldo(self.prateleira_do_cliente), 5)

    def test_tipo_interno_da_consignacao_cruza_a_fronteira(self):
        """COM/IN e afins são internos e saem da prateleira do cliente de
        propósito: a cerca é só do INT do armazém."""
        retorno = self.env['stock.picking.type'].create({
            'name': 'Retorno de teste', 'code': 'internal',
            'sequence_code': 'TSTIN', 'company_id': self.company.id,
            'warehouse_id': self.warehouse.id,
            'default_location_src_id': self.prateleira_do_cliente.id,
            'default_location_dest_id': self.raiz.id})
        picking = self.env['stock.picking'].create({
            'picking_type_id': retorno.id,
            'location_id': self.prateleira_do_cliente.id,
            'location_dest_id': self.outra.id,
            'move_ids': [(0, 0, {
                'product_id': self.livro.id, 'product_uom_qty': 5,
                'product_uom': self.livro.uom_id.id,
                'location_id': self.prateleira_do_cliente.id,
                'location_dest_id': self.outra.id})],
        })
        self.assertFalse(picking.is_shelf_transfer)
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        self.assertEqual(self._saldo(self.outra), 5)

    def test_realocar_recusa_a_prateleira_do_cliente(self):
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.livro.id),
            ('location_id', '=', self.prateleira.id)])
        wiz = self.env['stock.quant.relocate'].create({
            'quant_ids': [(6, 0, quant.ids)],
            'dest_location_id': self.prateleira_do_cliente.id})
        with self.assertRaises(UserError):
            wiz.action_relocate_quants()
        self.assertEqual(self._saldo(self.prateleira), 329)
