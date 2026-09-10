# -*- coding: utf-8 -*-
"""A diferença do retorno, das duas pontas em que ela pode nascer.

A volta tem duas pernas, e cada uma perde de um jeito:

  - no DESPACHO (a praça embala): a mesa tinha 25 e foram 20 para a caixa. Os
    5 nunca saíram da mesa. Alguém contou errado, alguém levou, alguém deixou
    embaixo do balcão -- e ninguém sabe qual ainda;
  - na CHEGADA (o armazém abre a caixa): saíram 20 e chegaram 18.

As duas viram perda "Não voltou (a explicar)", e nenhuma das duas baixa
estoque na hora: o exemplar fica onde está -- na mesa ou no trânsito -- até
alguém dizer o que houve. Quando diz, a baixa sai DE ONDE ELE ESTÁ.

Este arquivo existe porque o dono viu a volta chegar curta e perguntou onde a
diferença ia parar. Ia parar em lugar nenhum.
"""
from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs')
class TestRetornoCurto(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.armazem = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.livro = cls.env['product.product'].create({
            'name': 'Título da Volta', 'type': 'consu', 'is_storable': True,
            'standard_price': 30.0})
        cls.env['stock.quant']._update_available_quantity(
            cls.livro, cls.armazem.lot_stock_id, 200)

    # --- cenário ---------------------------------------------------------
    def _na_praca(self, qty=25):
        """Feira montada e conferida: a mesa tem `qty` exemplares de verdade."""
        fair = self.env['event.fair'].create({
            'name': 'Feira da Volta', 'date_start': date.today(),
            'date_end': date.today(), 'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': qty})]})
        fair.action_plan()
        saida = fair.action_ship()
        saida.action_assign()
        for move in saida.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        saida.button_validate()
        fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt'
            and p.state != 'done').action_fair_check()
        self.assertEqual(fair.line_ids.qty_on_shelf, qty)
        return fair

    def _validar(self, picking, quantidade=None):
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = (move.product_uom_qty if quantidade is None
                             else quantidade)
            move.picked = True
        picking.button_validate()
        return picking

    def _fechar_o_dia(self, fair):
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = dia.line_ids.qty_expected
        dia.action_close()

    def _na_mesa(self, fair):
        return self.livro.with_context(
            location=fair.stock_location_id.id,
            company_id=self.company.id).qty_available

    def _no_transito(self, fair):
        return self.livro.with_context(
            location=fair._get_transit_location().id,
            company_id=self.company.id).qty_available

    # --- a falta no DESPACHO de volta ------------------------------------
    def test_what_never_went_into_the_box_becomes_a_loss(self):
        fair = self._na_praca(25)
        self._fechar_o_dia(fair)
        despacho = fair.action_return()
        self.assertEqual(despacho.fair_operation, 'return_dispatch')

        self._validar(despacho, quantidade=20)   # cinco ficaram para trás

        perda = fair.loss_ids
        self.assertEqual(len(perda), 1)
        self.assertEqual(perda.qty, 5)
        self.assertEqual(perda.reason, 'not_returned')
        self.assertEqual(perda.stage, 'fair',
                         "Não saiu da mesa: o estágio é a feira, não o "
                         "trânsito")
        self.assertTrue(perda.to_explain)
        self.assertEqual(perda.value, 150.0, "Cinco a trinta reais de custo")
        self.assertEqual(perda.picking_id, despacho)
        self.assertFalse(perda.write_off_picking_id,
                         "Registrar não é baixar")
        self.assertEqual(self._na_mesa(fair), 5,
                         "Os cinco continuam onde estavam até alguém "
                         "explicar")

    def test_explaining_takes_them_off_the_table(self):
        fair = self._na_praca(25)
        self._fechar_o_dia(fair)
        self._validar(fair.action_return(), quantidade=20)
        perda = fair.loss_ids

        perda.reason = 'missing'

        self.assertTrue(perda.write_off_picking_id)
        self.assertEqual(perda.write_off_picking_id.state, 'done')
        self.assertEqual(
            perda.write_off_picking_id.move_ids.location_id,
            fair.stock_location_id,
            "A baixa sai DA MESA, que é onde o exemplar estava")
        self.assertEqual(self._na_mesa(fair), 0)
        self.assertEqual(fair.qty_lost, 5)
        self.assertFalse(perda.to_explain)

    def test_a_courtesy_goes_to_the_customer_not_to_the_bin(self):
        """Livro que foi para a mão de alguém não é descarte."""
        fair = self._na_praca(25)
        self._fechar_o_dia(fair)
        self._validar(fair.action_return(), quantidade=20)
        perda = fair.loss_ids
        perda.reason = 'courtesy'
        baixa = perda.write_off_picking_id
        self.assertEqual(baixa.fair_operation, 'sale')
        self.assertEqual(baixa.move_ids.location_dest_id,
                         self.env.ref('stock.stock_location_customers'))
        self.assertEqual(self._na_mesa(fair), 0)

    # --- a falta na CHEGADA, e as duas juntas -----------------------------
    def test_the_two_shortfalls_of_one_return_live_side_by_side(self):
        """Cinco ficaram na mesa e dois sumiram na estrada: duas perdas."""
        fair = self._na_praca(25)
        self._fechar_o_dia(fair)
        self._validar(fair.action_return(), quantidade=20)
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'return' and p.state != 'done')
        self._validar(chegada, quantidade=18)

        perdas = fair.loss_ids
        self.assertEqual(len(perdas), 2)
        por_estagio = {p.stage: p for p in perdas}
        self.assertEqual(por_estagio['fair'].qty, 5,
                         "Os que não entraram na caixa")
        self.assertEqual(por_estagio['transit'].qty, 2,
                         "Os que sumiram entre a feira e o armazém")
        self.assertEqual(set(perdas.mapped('reason')), {'not_returned'})
        self.assertEqual(self._na_mesa(fair), 5)
        self.assertEqual(self._no_transito(fair), 2)
        self.assertEqual(fair.qty_returned, 18,
                         "Voltaram dezoito, que é o que o armazém contou")

    def test_explaining_both_empties_the_fair(self):
        """Explicadas as duas, a feira não guarda exemplar em lugar nenhum."""
        fair = self._na_praca(25)
        self._fechar_o_dia(fair)
        self._validar(fair.action_return(), quantidade=20)
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'return' and p.state != 'done')
        self._validar(chegada, quantidade=18)

        fair.loss_ids.write({'reason': 'missing'})

        self.assertEqual(self._na_mesa(fair), 0)
        self.assertEqual(self._no_transito(fair), 0)
        self.assertEqual(fair.qty_lost, 7)
        self.assertEqual(fair.line_ids.qty_on_shelf, 0,
                         "Feira que voltou não tem mesa")
        self.assertFalse(fair.loss_ids.filtered('to_explain'))

    def test_a_full_return_loses_nothing(self):
        """O caminho feliz continua feliz: volta inteira, perda nenhuma."""
        fair = self._na_praca(25)
        self._fechar_o_dia(fair)
        self._validar(fair.action_return())
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'return' and p.state != 'done')
        self._validar(chegada)
        self.assertFalse(fair.loss_ids)
        self.assertEqual(fair.qty_returned, 25)
        self.assertEqual(self._na_mesa(fair), 0)

    def test_the_arrival_still_refuses_to_run_ahead_of_the_dispatch(self):
        """A trava de setembro continua de pé com a mudança de hoje."""
        from odoo.exceptions import UserError
        fair = self._na_praca(25)
        self._fechar_o_dia(fair)
        fair.action_return()                     # despacho NÃO validado
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'return')
        self.assertFalse(chegada.fair_on_the_road)
        with self.assertRaises(UserError):
            chegada.button_validate()
        self.assertFalse(fair.loss_ids,
                         "E a tentativa não pode inventar perda nenhuma")

    # --- a mesma doença na IDA -------------------------------------------
    def test_what_the_warehouse_could_not_find_is_not_the_fairs_loss(self):
        """Livro que nunca saiu do depósito não é perda de quem está na praça.

        A ida tem as mesmas duas pernas. Se o armazém acha 18 dos 25, a
        chegada tem de passar a esperar 18 -- e não 25, com sete "não
        recebidos" no colo de quem está na feira.
        """
        fair = self.env['event.fair'].create({
            'name': 'Feira da Ida Curta', 'date_start': date.today(),
            'date_end': date.today(), 'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': 25})]})
        fair.action_plan()
        saida = fair.action_ship()

        self._validar(saida, quantidade=18)      # o depósito só achou 18

        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt')
        self.assertEqual(
            sum(chegada.move_ids.mapped('product_uom_qty')), 18,
            "A chegada tem de esperar o que saiu, e não o que foi planejado")
        self.assertFalse(fair.loss_ids,
                         "Nada se perdeu: o resto está no armazém")

        chegada.action_fair_check()
        self.assertEqual(fair.qty_sent, 18)
        self.assertFalse(fair.loss_ids)
        self.assertEqual(fair.line_ids.qty_planned, 25,
                         "E a grade continua pedindo 25: faltam 7 a despachar")

    def test_cancelling_the_dispatch_cancels_the_arrival(self):
        """Carga que não saiu não deixa chegada pendurada na praça.

        O depósito não valida uma remessa com zero (o Odoo recusa, e faz
        bem): ele CANCELA. E o cancelamento tem de descer pela corrente,
        senão a praça fica com uma chegada esperando carga que ninguém
        mandou.
        """
        fair = self.env['event.fair'].create({
            'name': 'Feira que não saiu', 'date_start': date.today(),
            'date_end': date.today(), 'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': 10})]})
        fair.action_plan()
        saida = fair.action_ship()
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt')

        saida.action_cancel()

        chegada.invalidate_recordset()
        self.assertEqual(chegada.state, 'cancel')
        self.assertFalse(fair.loss_ids)
        self.assertEqual(fair.qty_sent, 0)
        self.assertEqual(fair.line_ids.qty_requested, 0,
                         "E a grade volta a mostrar os dez a despachar")
