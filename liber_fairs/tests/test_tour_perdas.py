# -*- coding: utf-8 -*-
"""Explicar a perda na tela, com o perfil de quem explica.

A falta nasce sozinha, no aperto da feira, e fica em Perdas com o status "a
explicar". Explicar é o ato que fecha o ciclo: escolhido o motivo, o exemplar
sai de onde estava. Este tour anda esse caminho na tela — e ele já pegou uma
coisa que o ORM não vê: um campo com widget de crachá não se edita na lista,
e a fila ficaria sem saída.
"""
from datetime import date

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs_tour')
class TestTourPerdas(HttpCase):

    def test_explicar_a_perda_na_tela(self):
        company = self.env.company
        armazem = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        livro = self.env['product.product'].create({
            'name': 'Título da Perda', 'type': 'consu', 'is_storable': True,
            'standard_price': 40.0})
        self.env['stock.quant']._update_available_quantity(
            livro, armazem.lot_stock_id, 40)

        # feira montada, conferida e devolvida CURTA: três ficaram na mesa
        fair = self.env['event.fair'].create({
            'name': 'Feira da Perda', 'date_start': date.today(),
            'date_end': date.today(), 'company_id': company.id,
            'line_ids': [(0, 0, {'product_id': livro.id, 'qty_planned': 12})]})
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
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = dia.line_ids.qty_expected
        dia.action_close()
        despacho = fair.action_return()
        despacho.action_assign()
        for move in despacho.move_ids:
            move.quantity = move.product_uom_qty - 3
            move.picked = True
        despacho.button_validate()

        perda = fair.loss_ids
        self.assertEqual(len(perda), 1)
        self.assertTrue(perda.to_explain)
        self.assertFalse(perda.write_off_picking_id)
        na_mesa = livro.with_context(
            location=fair.stock_location_id.id,
            company_id=company.id).qty_available
        self.assertEqual(na_mesa, 3, "Os três continuam na mesa")

        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Quem explica', 'login': 'tour_perdas',
                'password': 'tour_perdas', 'lang': 'pt_BR',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': [
                    (4, self.env.ref('liber_fairs.group_fair_manager').id)]})
        self.assertTrue(usuario)

        self.start_tour('/odoo', 'fair_losses_tour', login='tour_perdas')

        # O tour prova a TELA (a fila abre, a linha edita, o motivo é
        # editável). O efeito de explicar prova-se aqui, pelo ORM -- e é o
        # mesmo caminho que a tela dispara ao gravar.
        perda.reason = 'missing'

        self.assertFalse(perda.to_explain)
        self.assertTrue(perda.write_off_picking_id,
                        "Explicar tem de BAIXAR o exemplar")
        self.assertEqual(perda.write_off_picking_id.move_ids.location_id,
                         fair.stock_location_id,
                         "Da mesa, que é onde eles estavam")
        na_mesa = livro.with_context(
            location=fair.stock_location_id.id,
            company_id=company.id).qty_available
        self.assertEqual(na_mesa, 0, "A mesa esvaziou")
