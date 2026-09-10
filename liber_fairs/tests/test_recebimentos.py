# -*- coding: utf-8 -*-
"""Recebimentos: duas colunas e um ok.

Não é rotina de depósito, é rotina de confusão de feira. A caixa chega no
meio do movimento, e quem recebe não vai abrir transferência por
transferência para digitar a mesma quantidade que já está escrita. Seleciona,
aperta, e fica registrado quem contou e quando.

A falta, quando houver, é registrada como perda SEM motivo. A explicação vem
depois, em Perdas, onde há tempo de pensar — perda sem motivo é uma pergunta
em aberto, e é melhor do que um exemplar que ninguém sabe que faltou.
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs')
class TestRecebimentos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.livro = cls.env['product.product'].create({
            'name': 'Título do Recebimento', 'type': 'consu',
            'is_storable': True, 'standard_price': 25.0})
        cls.env['stock.quant']._update_available_quantity(
            cls.livro, cls.warehouse.lot_stock_id, 100)

    def _fair(self, qty=10):
        fair = self.env['event.fair'].create({
            'name': 'Feira do Recebimento',
            'date_start': date(2026, 9, 20), 'date_end': date(2026, 9, 20),
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': qty})]})
        fair.action_plan()
        return fair

    def _despachar(self, fair):
        saida = fair.action_ship()
        saida.action_assign()
        for move in saida.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        saida.with_context(
            skip_backorder=True,
            picking_ids_not_to_backorder=saida.ids).button_validate()
        return saida

    def _chegada(self, fair):
        return fair.picking_ids.filtered(
            lambda p: p.fair_is_arrival and p.state not in ('done', 'cancel'))

    # --- as duas colunas --------------------------------------------------
    def test_two_columns_received_and_checked(self):
        """Recebido é o que quem mandou diz; conferido é o que se contou."""
        fair = self._fair(10)
        self._despachar(fair)
        chegada = self._chegada(fair)
        self.assertTrue(chegada, "A chegada é a transferência a conferir")
        self.assertTrue(chegada.fair_is_arrival)
        self.assertEqual(chegada.fair_qty_received, 10)
        self.assertEqual(chegada.fair_qty_checked, 10,
                         "A reserva já sugere o que se espera contar")
        self.assertEqual(chegada.fair_shortfall, 0)

    def test_the_general_ok_confirms_and_signs(self):
        """Um clique confere a carga e assina quem contou."""
        fair = self._fair(10)
        self._despachar(fair)
        chegada = self._chegada(fair)
        antes_feira = len(fair.message_ids)
        chegada.action_fair_check()
        self.assertEqual(chegada.state, 'done')
        self.assertEqual(chegada.fair_qty_checked, 10)
        self.assertEqual(chegada.fair_checked_by_id, self.env.user,
                         "Conferência sem assinatura é conferência que "
                         "ninguém fez")
        self.assertTrue(chegada.fair_checked_on)
        self.assertEqual(fair.qty_sent, 10, "E o estoque chegou na mesa")
        # o registro sai nos dois lados: no movimento e na feira
        self.assertIn('checked by', ' '.join(chegada.message_ids.mapped('body')))
        self.assertGreater(len(fair.message_ids), antes_feira,
                           "A equipe da feira lê o histórico da feira")

    def test_several_loads_in_one_click(self):
        """Seleciona as linhas e aperta uma vez: é o ponto da tela."""
        fair = self._fair(10)
        self._despachar(fair)
        fair.line_ids.qty_planned = 16
        self._despachar(fair)
        chegadas = self._chegada(fair)
        self.assertEqual(len(chegadas), 2)
        chegadas.action_fair_check()
        self.assertEqual(set(chegadas.mapped('state')), {'done'})
        self.assertEqual(fair.qty_sent, 16)

    # --- a falta ----------------------------------------------------------
    def test_a_short_load_becomes_an_open_question(self):
        """Faltou: registra-se sozinho, sem motivo, e explica-se depois.

        E sem PEDIDO EM ESPERA: em feira nada fica pendurado esperando --
        chegou ou não chegou. O diálogo do núcleo não aparece, e a falta é
        medida ANTES de o movimento fechar, porque depois o núcleo reescreve
        a demanda para o que foi concluído e a diferença deixa de existir.
        """
        fair = self._fair(10)
        self._despachar(fair)
        chegada = self._chegada(fair)
        chegada.action_assign()
        for move in chegada.move_ids:
            move.quantity = 7
            move.picked = True
        # validado pelo caminho normal da tela, SEM contexto nenhum
        res = chegada.button_validate()
        self.assertNotEqual(res, False) if res else None
        self.assertEqual(chegada.state, 'done')
        self.assertEqual(
            len(fair.picking_ids.filtered(
                lambda p: p.fair_operation == 'receipt')), 1,
            "Nenhum pedido em espera nasceu")
        perdas = fair.loss_ids
        self.assertEqual(len(perdas), 1)
        self.assertEqual(perdas.qty, 3)
        self.assertEqual(perdas.reason, 'not_received',
                         "No meio da feira ninguém para para classificar: "
                         "fica 'Não recebido', que é o que se sabe")
        self.assertTrue(perdas.to_explain)
        self.assertEqual(perdas.unit_cost, 25.0,
                         "Mas o custo é congelado na hora")
        self.assertEqual(perdas.stage, 'fair')
        self.assertEqual(fair.qty_sent, 7, "Chegaram sete na mesa")

    def test_what_does_not_come_back_is_a_return_loss(self):
        """A conferência do RETORNO: o que a mesa mandou e não chegou na caixa.

        Mesma tela e mesmo clique da chegada -- a diferença é o nome do que
        se registra. Na ida, "não recebido"; na volta, "não voltou". Nenhum
        dos dois baixa estoque: os dois são perguntas em Perdas.
        """
        fair = self._fair(10)
        self._despachar(fair)
        self._chegada(fair).action_fair_check()

        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 6
        dia.action_close()

        saida_de_volta = fair.action_return()
        self.assertEqual(saida_de_volta.fair_operation, 'return_dispatch')
        saida_de_volta.action_assign()
        for move in saida_de_volta.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        saida_de_volta.button_validate()

        volta = self._chegada(fair)
        self.assertEqual(volta.fair_operation, 'return')
        volta.action_assign()
        for move in volta.move_ids:
            move.quantity = 4          # a mesa mandou 6, a caixa trouxe 4
            move.picked = True
        volta.button_validate()

        self.assertEqual(volta.state, 'done')
        perda = fair.loss_ids
        self.assertEqual(len(perda), 1)
        self.assertEqual(perda.qty, 2)
        self.assertEqual(perda.reason, 'not_returned',
                         "Falta na volta é perda de RETORNO, não da ida")
        self.assertEqual(perda.stage, 'transit')
        self.assertTrue(perda.to_explain, "Continua sendo pergunta em aberto")
        self.assertEqual(perda.value, 50.0)
        self.assertEqual(fair.qty_returned, 4)
        # A MESA FECHA EM ZERO, e é aqui que a conta antes mentia: descontando
        # pela chegada no armazém, a feira encerrava dizendo "na mesa 2" de
        # uma mesa que já não existe. Os dois exemplares são perda -- estão em
        # Perdas, à espera de explicação --, não estoque na praça.
        self.assertEqual(fair.qty_on_shelf, 0,
                         "Feira que voltou não tem mesa")

        # e explicar a falta tira os dois do trânsito
        transito = fair._get_transit_location()
        self.assertEqual(self.livro.with_context(
            location=transito.id, company_id=fair.company_id.id
        ).qty_available, 2)
        perda.reason = 'missing'
        self.assertEqual(self.livro.with_context(
            location=transito.id, company_id=fair.company_id.id
        ).qty_available, 0, "O trânsito esvazia quando alguém explica")
        self.assertEqual(fair.qty_lost, 2)
        self.assertEqual(fair.qty_on_shelf, 0, "E a mesa segue em zero")

    def test_a_return_loss_writes_nothing_off(self):
        """Registrar não é baixar. O que fazer com isso se decide depois."""
        fair = self._fair(10)
        perda = self.env['event.fair.loss'].create({
            'fair_id': fair.id, 'product_id': self.livro.id, 'qty': 2,
            'reason': 'not_returned', 'stage': 'transit'})
        from odoo.addons.liber_fairs.models.event_fair_loss import DESTINO
        self.assertNotIn('not_returned', DESTINO,
                         "Sem destino de estoque: nada se move enquanto "
                         "ninguém disser o que houve")
        self.assertTrue(perda.to_explain)

    def test_the_reason_can_be_filled_later(self):
        """Perdas é onde há tempo de pensar."""
        fair = self._fair(10)
        perda = self.env['event.fair.loss'].create({
            'fair_id': fair.id, 'product_id': self.livro.id, 'qty': 3})
        self.assertEqual(perda.reason, 'not_received',
                         "Nasce como pergunta em aberto")
        self.assertTrue(perda.to_explain)
        perda.reason = 'missing'
        self.assertEqual(perda.reason, 'missing')
        self.assertFalse(perda.to_explain, "Explicada, sai da fila")
        self.assertEqual(perda.value, 75.0)
        self.assertEqual(fair.loss_value, 75.0)

    def test_an_arrival_cannot_be_confirmed_before_the_load_leaves(self):
        """O estrago de 09/09: 107 exemplares que viraram 8, e 99 perdas.

        A chegada estava "Pronto" porque o trânsito guardava livro de OUTRA
        operação, e como feira nunca cria pedido em espera, validar fechou o
        movimento com o pouco que havia — o resto virou perda "Não voltou",
        num retorno em que ninguém tinha perdido nada.

        A regra de não criar pedido em espera continua certa. O que faltava
        era não deixá-la ser aplicada a uma carga que ainda nem saiu.
        """
        fair = self._fair(10)
        fair.action_ship()                     # despacha, mas o armazém NÃO valida
        chegada = self._chegada(fair)
        self.assertTrue(chegada)
        self.assertFalse(chegada.fair_on_the_road,
                         "Nada saiu: esta chegada não está a caminho")

        with self.assertRaises(UserError):
            chegada.button_validate()
        with self.assertRaises(UserError):
            chegada.action_fair_check()

        self.assertFalse(fair.loss_ids,
                         "E nenhuma perda pode ter nascido dessa tentativa")

    def test_the_arrival_shows_up_once_the_load_leaves(self):
        """Depois que o depósito valida, aí sim a praça confere."""
        fair = self._fair(10)
        self._despachar(fair)
        chegada = self._chegada(fair)
        self.assertTrue(chegada.fair_on_the_road)
        chegada.action_fair_check()
        self.assertEqual(chegada.state, 'done')
        self.assertEqual(fair.qty_sent, 10)

    # --- erro -------------------------------------------------------------
    def test_only_arrivals_are_checked_here(self):
        """A saída do armazém não se confere aqui: ela é despacho."""
        fair = self._fair(10)
        saida = fair.action_ship()
        self.assertFalse(saida.fair_is_arrival)
        with self.assertRaises(UserError):
            saida.action_fair_check()


@tagged('post_install', '-at_install', 'liber_fairs')
class TestPerdaNoTransito(TestRecebimentos):
    """A perna que faltava: explicar a falta tira o exemplar do trânsito.

    A falta acusada na conferência deixa o exemplar parado no meio da viagem
    -- e é assim que tem de ser, porque ninguém sabe ainda o que houve. O
    buraco era o depois: escolher o motivo mudava o registro e não mexia no
    estoque, e o exemplar ficava no trânsito para sempre.
    """

    def _transito(self, fair):
        # O corredor DESTA feira. Ler o trânsito genérico da empresa era o
        # que a versão anterior fazia, e é justamente o que deixou uma perna
        # pegar carga de outra.
        return fair._get_transit_location()

    def _no_transito(self, fair, produto=None):
        local = self._transito(fair)
        return (produto or self.livro).with_context(
            location=local.id, company_id=fair.company_id.id).qty_available

    def _ida_curta(self, planejado=10, chegou=7):
        fair = self._fair(planejado)
        self._despachar(fair)
        chegada = self._chegada(fair)
        chegada.action_assign()
        for move in chegada.move_ids:
            move.quantity = chegou
            move.picked = True
        chegada.button_validate()
        return fair

    def test_the_missing_copies_wait_in_transit(self):
        """Antes de explicar, o exemplar fica onde está. E isso é correto."""
        fair = self._ida_curta()
        self.assertEqual(self._no_transito(fair), 3,
                         "Os três que não chegaram estão no trânsito")
        self.assertEqual(fair.line_ids.qty_on_shelf, 7,
                         "E não estão na mesa: a mesa recebeu sete")

    def test_explaining_takes_them_out_of_transit(self):
        fair = self._ida_curta()
        perda = fair.loss_ids
        self.assertFalse(perda.write_off_picking_id)

        perda.reason = 'missing'

        self.assertTrue(perda.write_off_picking_id,
                        "Explicada, a perda tem de gerar a baixa")
        self.assertEqual(perda.write_off_picking_id.state, 'done')
        self.assertEqual(self._no_transito(fair), 0,
                         "O trânsito tem de esvaziar")
        self.assertEqual(fair.qty_lost, 3)
        self.assertEqual(fair.line_ids.qty_on_shelf, 7,
                         "A mesa não muda: esses três nunca chegaram nela")
        self.assertFalse(perda.to_explain)

    def test_a_sale_reason_sends_them_to_the_customer(self):
        """Vendido e não lançado não é descarte: o livro foi para alguém."""
        fair = self._ida_curta()
        perda = fair.loss_ids
        perda.reason = 'sold'
        baixa = perda.write_off_picking_id
        self.assertEqual(baixa.fair_operation, 'sale')
        self.assertEqual(
            baixa.move_ids.location_dest_id,
            self.env.ref('stock.stock_location_customers'))
        self.assertEqual(self._no_transito(fair), 0)

    def test_explaining_twice_does_not_move_twice(self):
        fair = self._ida_curta()
        perda = fair.loss_ids
        perda.reason = 'missing'
        primeira = perda.write_off_picking_id
        perda.reason = 'damaged'
        self.assertEqual(perda.write_off_picking_id, primeira,
                         "Trocar o motivo de novo não pode baixar outra vez")
        self.assertEqual(fair.qty_lost, 3)

    def test_nothing_in_transit_records_the_reason_anyway(self):
        """Explicação atrasada não trava ninguém."""
        fair = self._ida_curta()
        perda = fair.loss_ids
        # alguém já tirou os exemplares do trânsito por fora
        local = self._transito(fair)
        quant = self.env['stock.quant'].sudo().search([
            ('location_id', '=', local.id),
            ('product_id', '=', self.livro.id)])
        quant = quant.with_context(inventory_mode=True)
        quant.inventory_quantity = 0
        quant.action_apply_inventory()

        perda.reason = 'damaged'

        self.assertEqual(perda.reason, 'damaged',
                         "O motivo se registra mesmo sem estoque a mover")
        self.assertFalse(perda.write_off_picking_id)

    def test_a_hand_written_loss_is_not_a_transit_loss(self):
        """Avaria da chuva fala da mesa, não do trânsito."""
        fair = self._ida_curta()
        mao = self.env['event.fair.loss'].create({
            'fair_id': fair.id, 'product_id': self.livro.id, 'qty': 1,
            'reason': 'not_received'})
        mao.reason = 'damaged'
        self.assertFalse(mao.write_off_picking_id,
                         "Sem conferência por trás, não há nada no trânsito "
                         "para tirar")
        self.assertEqual(self._no_transito(fair), 3,
                         "E o trânsito continua com os três da conferência")
