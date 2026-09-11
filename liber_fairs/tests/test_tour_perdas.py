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
        # O clique em Retorno já esvazia a mesa; a falta que sobra para
        # explicar na tela é a da ESTRADA -- o armazém conta três a menos.
        fair.action_return()
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'return' and p.state != 'done')
        chegada.action_assign()
        for move in chegada.move_ids:
            move.quantity = move.product_uom_qty - 3
            move.picked = True
        chegada.button_validate()

        perda = fair.loss_ids
        self.assertEqual(len(perda), 1)
        self.assertTrue(perda.to_explain)
        self.assertFalse(perda.write_off_picking_id)
        no_transito = livro.with_context(
            location=fair._get_transit_location().id,
            company_id=company.id).qty_available
        self.assertEqual(no_transito, 3, "Os três ficaram na estrada")

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
                         fair._get_transit_location(),
                         "Do trânsito, que é onde eles ficaram")
        na_mesa = livro.with_context(
            location=fair._get_transit_location().id,
            company_id=company.id).qty_available
        self.assertEqual(na_mesa, 0, "A mesa esvaziou")
