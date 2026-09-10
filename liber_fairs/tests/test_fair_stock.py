# -*- coding: utf-8 -*-
"""A fase 2: a localização fora do armazém, a reposição e o fechamento diário.

A regra que mais importa aqui é a primeira: o estoque na feira continua sendo
nosso (localização INTERNA, mantém valor no balanço) mas NÃO conta no "Em
mãos" do armazém, porque a raiz FEIRAS fica fora da árvore do armazém. Se
alguém um dia pendurar a raiz sob WH, o Em mãos passa a somar exemplar que
está a seiscentos quilômetros e ninguém pode vender pelo site. É calado, e por
isso tem teste.
"""
from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs')
class TestFairStock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.product = cls.env['product.product'].create({
            'name': 'Título de Feira',
            'type': 'consu',
            'is_storable': True,
            'list_price': 50.0,
        })
        cls.env['stock.quant']._update_available_quantity(
            cls.product, cls.stock_location, 100)
        cls.today = date(2026, 9, 20)

    def _fair(self, qty=10):
        return self.env['event.fair'].create({
            'name': 'Feira de Teste',
            'date_start': self.today,
            'date_end': self.today + timedelta(days=1),
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id, 'qty_planned': qty})],
        })

    def _entregar(self, fair):
        """A ida inteira: o armazém despacha e a feira confere a chegada.

        A ida tem duas pernas desde 08/09/2026 -- sem a segunda, o livro fica
        no trânsito e não na mesa, que é exatamente o ponto.
        """
        saidas = fair.action_ship()
        self._validate(saidas)
        self._receber(fair)
        return saidas

    def _receber_retorno(self, fair):
        """A segunda perna da VOLTA: o armazém confere o que chegou."""
        entradas = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'return'
            and p.state not in ('done', 'cancel'))
        if entradas:
            self._validate(entradas)
        return entradas

    def _receber(self, fair):
        """Confere na praça o que estava a caminho."""
        recebimentos = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt'
            and p.state not in ('done', 'cancel'))
        if recebimentos:
            self._validate(recebimentos)
        return recebimentos

    def _validate(self, picking):
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()
        return picking

    # --- a localização ----------------------------------------------------
    def test_fair_location_is_internal_and_outside_the_warehouse(self):
        """Nosso estoque, fora da árvore do armazém."""
        fair = self._fair()
        fair.action_plan()
        location = fair.stock_location_id
        self.assertEqual(location.usage, 'internal',
                         "O que está na feira ainda é nosso: interna, não virtual")
        root = location.location_id
        self.assertTrue(root.is_fair_root)
        self.assertFalse(root.location_id,
                         "A raiz FEIRAS tem de ficar FORA do armazém, senão o "
                         "Em mãos passa a somar o que está na praça")
        self.assertFalse(location.warehouse_id,
                         "A localização da feira não pertence a armazém nenhum")

    def test_two_fairs_get_two_locations_under_one_root(self):
        primeira = self._fair()
        segunda = self._fair()
        primeira.action_plan()
        segunda.action_plan()
        self.assertNotEqual(primeira.stock_location_id,
                            segunda.stock_location_id)
        self.assertEqual(primeira.stock_location_id.location_id,
                         segunda.stock_location_id.location_id)

    # --- remessa e reposição ---------------------------------------------
    def test_shipment_moves_stock_to_the_fair(self):
        fair = self._fair(qty=10)
        fair.action_plan()
        picking = fair.action_ship()
        self.assertEqual(picking.fair_operation, 'shipment')
        self.assertEqual(picking.picking_type_id.sequence_code, 'FEIRA/OUT')
        self._validate(picking)
        self.assertEqual(fair.qty_sent, 0,
                         "Saiu do armazém não é o mesmo que chegou na mesa")
        self.assertEqual(fair.line_ids.qty_in_transit, 10)
        self._receber(fair)
        self.assertEqual(fair.qty_sent, 10)
        self.assertEqual(fair.qty_on_shelf, 10)
        quant = self.env['stock.quant'].search([
            ('location_id', '=', fair.stock_location_id.id),
            ('product_id', '=', self.product.id)])
        self.assertEqual(sum(quant.mapped('quantity')), 10,
                         "Os dez exemplares tinham de estar na mesa")

    def test_replenishment_sends_only_the_difference(self):
        """Evento de vários dias pede reposição: sobe o planejado, despacha de novo."""
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        fair.line_ids.qty_planned = 16
        segunda = fair.action_ship()
        self.assertEqual(len(segunda), 1)
        self.assertEqual(sum(segunda.move_ids.mapped('product_uom_qty')), 6,
                         "A reposição manda a DIFERENÇA, não a grade inteira")
        self._validate(segunda)
        self._receber(fair)
        self.assertEqual(fair.qty_sent, 16)
        self.assertEqual(fair.qty_on_shelf, 16)
        self.assertEqual(
            len(fair.picking_ids.filtered(
                lambda p: p.fair_operation == 'shipment')), 2,
            "Uma feira, N remessas, uma localização só")
        self.assertEqual(
            fair.picking_ids.filtered(
                lambda p: p.fair_operation == 'receipt'
            ).mapped('location_dest_id'),
            fair.stock_location_id)

    def test_shipping_with_nothing_pending_is_refused(self):
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        with self.assertRaises(UserError):
            fair.action_ship()

    # --- fechamento diário ------------------------------------------------
    def test_daily_closing_deduces_what_was_sold(self):
        """Conta-se o que sobrou; o vendido é deduzido e vira movimento."""
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        self.assertEqual(dia.line_ids.qty_expected, 10)
        # Sobraram sete na mesa: venderam três.
        dia.line_ids.qty_counted = 7
        dia.action_close()
        self.assertEqual(dia.state, 'closed')
        self.assertEqual(dia.qty_sold, 3)
        self.assertTrue(dia.picking_id)
        self.assertEqual(dia.picking_id.fair_operation, 'sale')
        self.assertEqual(dia.picking_id.state, 'done')
        self.assertEqual(fair.qty_sold, 3)
        self.assertEqual(fair.qty_on_shelf, 7,
                         "O saldo da localização tem de bater com a mesa")

    def test_second_day_opens_from_the_first_day_balance(self):
        """O dia seguinte abre com o que sobrou, e a reposição entra no meio."""
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        primeiro, segundo = fair.day_ids[0], fair.day_ids[1]
        primeiro.action_fill()
        primeiro.line_ids.qty_counted = 7
        primeiro.action_close()
        # Reposição durante a feira: mais seis chegam para o segundo dia.
        fair.line_ids.qty_planned = 16
        self._entregar(fair)
        segundo.action_fill()
        self.assertEqual(segundo.line_ids.qty_expected, 13,
                         "Abertura do segundo dia = 7 que sobraram + 6 repostos")
        segundo.line_ids.qty_counted = 5
        segundo.action_close()
        self.assertEqual(fair.qty_sold, 11)
        self.assertEqual(fair.qty_on_shelf, 5)

    # --- erro -------------------------------------------------------------
    def test_counting_more_than_the_table_holds_is_refused(self):
        """Contagem acima do esperado não é venda negativa: é erro."""
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 12
        with self.assertRaises(UserError):
            dia.action_close()

    def test_closing_the_same_day_twice_is_refused(self):
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 8
        dia.action_close()
        with self.assertRaises(UserError):
            dia.action_close()

    # --- retorno ----------------------------------------------------------
    def test_return_brings_back_what_is_left(self):
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 6
        dia.action_close()
        retorno = fair.action_return()
        self.assertEqual(retorno.fair_operation, 'return_dispatch')
        self.assertEqual(sum(retorno.move_ids.mapped('product_uom_qty')), 6)
        self._validate(retorno)
        self._receber_retorno(fair)
        self.assertEqual(fair.state, 'returned')
        self.assertEqual(fair.qty_returned, 6)
        self.assertEqual(fair.qty_on_shelf, 0,
                         "Enviado 10, vendido 4, voltou 6: a mesa tem de zerar")
        quant = self.env['stock.quant'].search([
            ('location_id', '=', fair.stock_location_id.id),
            ('product_id', '=', self.product.id)])
        self.assertEqual(sum(quant.mapped('quantity')), 0)

    def test_the_warehouse_cards_come_back_if_somebody_archived_them(self):
        """Despacho sem cartão é despacho para ninguém.

        Aconteceu: uma faxina arquivou TODOS os tipos de operação de feira,
        inclusive os dois que a logística trabalha. Ele despachou, foi ao
        Inventário e não viu nada -- e acabou validando a remessa sozinho,
        que é exatamente o contrário do que a segunda perna existe para
        garantir.
        """
        company = self.company
        saida = company._get_fair_shipment_operation_type()
        volta = company._get_fair_return_operation_type()
        (saida | volta).sudo().write({'active': False})

        # basta pedir o tipo de novo: ele volta para a bancada
        self.assertTrue(company._get_fair_shipment_operation_type().active,
                        "A remessa para feira é trabalho de armazém")
        self.assertTrue(company._get_fair_return_operation_type().active,
                        "A carga que volta também")

    # --- a bancada da logística -------------------------------------------
    def test_only_the_two_real_operations_show_on_the_overview(self):
        """A Visão geral do Inventário é bancada, não vitrine.

        Cada cartão ali é trabalho que alguém pega. A logística de feira
        trabalha DOIS movimentos: a carga que sai e a que volta. "Venda em
        feira" é a contrapartida do fechamento diário, gerada e concluída
        pelo sistema no mesmo clique, sem caixa nenhuma se mexendo -- um
        cartão desse só faz a pessoa abrir para descobrir que não há nada a
        fazer.
        """
        company = self.company
        remessa = company._get_fair_shipment_operation_type()
        retorno = company._get_fair_return_operation_type()
        venda = company._get_fair_sale_operation_type()
        perda = company._get_fair_loss_operation_type()
        self.assertTrue(remessa.active, "A carga que sai é trabalho")
        self.assertTrue(retorno.active, "A carga que volta é trabalho")
        self.assertFalse(venda.active,
                         "Venda em feira não é trabalho de armazém")
        self.assertFalse(perda.active,
                         "Perda em feira não é trabalho de armazém")

    def test_an_archived_type_still_moves_stock(self):
        """Arquivar tira o cartão, não a operação: o fechamento continua."""
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 6
        dia.action_close()
        self.assertEqual(dia.picking_id.state, 'done')
        self.assertFalse(dia.picking_id.picking_type_id.active)
        self.assertEqual(fair.qty_sold, 4)
        self.assertEqual(fair.qty_on_shelf, 6)

    # --- reposição pedida no fechamento -----------------------------------
    def test_the_replenishment_is_asked_where_it_is_discovered(self):
        """Pedir reposição na contagem do dia, não na aba da grade.

        É a contagem do fim do dia que mostra o que acabou. Pedir na grade
        obriga quem está no balcão a lembrar de cabeça o que faltou e a
        procurar cada título outra vez numa lista de dezenas.
        """
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 2      # vendeu 8, sobraram 2
        dia.line_ids.qty_replenish = 9    # manda mais 9 para amanhã
        dia.action_close()
        self.assertEqual(dia.qty_sold, 8)
        self.assertTrue(dia.replenish_picking_ids,
                        "Fechar com a coluna preenchida tem de despachar")
        reposicao = dia.replenish_picking_ids
        self.assertEqual(reposicao.fair_operation, 'shipment')
        self.assertEqual(
            sum(reposicao.move_ids.mapped('product_uom_qty')), 9)
        entrada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt'
            and p.state not in ('done', 'cancel'))[-1:]
        self.assertEqual(entrada.location_dest_id, fair.stock_location_id,
                         "A reposição vai para a MESMA mesa")
        self.assertEqual(fair.line_ids.qty_planned, 19,
                         "A grade sobe: 10 planejados mais 9 repostos")
        self.assertEqual(dia.line_ids.qty_replenish, 0,
                         "A coluna é o pedido de agora, não histórico")
        self._validate(reposicao)
        self._receber(fair)
        self.assertEqual(fair.qty_on_shelf, 11,
                         "Dois que sobraram mais nove que chegaram")

    def test_a_closed_day_refuses_a_replenishment(self):
        """Dia fechado é dia fechado, sem meia porta aberta.

        Precisando de mais livro depois de fechar, o pedido é da FEIRA: sobe
        a grade e despacha de lá. Deixar o dia aceitar pedido depois de
        contado faria o número dele deixar de ser o retrato daquele dia.
        """
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 3
        dia.action_close()
        self.assertFalse(dia.replenish_picking_ids)
        dia.line_ids.qty_replenish = 5
        with self.assertRaises(UserError):
            dia.action_replenish()
        # o caminho que continua aberto é o da feira
        fair.line_ids.qty_planned += 5
        self.assertEqual(
            sum(fair.action_ship().move_ids.mapped('product_uom_qty')), 5)

    def test_asking_for_nothing_is_refused(self):
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        with self.assertRaises(UserError):
            dia.action_replenish()

    def test_a_sold_out_title_stays_on_the_table_with_a_zero(self):
        """O esgotado é justamente o que se quer repor.

        Sumir da contagem obrigaria quem está no balcão a lembrar de cabeça o
        que acabou. O zero na mesa é informação, não ruído.
        """
        outro = self.env['product.product'].create({
            'name': 'Segundo Título', 'type': 'consu', 'is_storable': True})
        self.env['stock.quant']._update_available_quantity(
            outro, self.stock_location, 100)
        fair = self._fair(qty=10)
        self.env['event.fair.line'].create({
            'fair_id': fair.id, 'product_id': outro.id, 'qty_planned': 4})
        fair.action_plan()
        self._entregar(fair)
        primeiro = fair.day_ids[0]
        primeiro.action_fill()
        # o segundo título esgota no primeiro dia
        for linha in primeiro.line_ids:
            linha.qty_counted = 0 if linha.product_id == outro else 8
        primeiro.action_close()
        segundo = fair.day_ids[1]
        segundo.action_fill()
        produtos = segundo.line_ids.mapped('product_id')
        self.assertIn(outro, produtos,
                      "O esgotado tem de continuar na mesa, com zero")
        linha_esgotada = segundo.line_ids.filtered(
            lambda l: l.product_id == outro)
        self.assertEqual(linha_esgotada.qty_expected, 0)
        self.assertEqual(linha_esgotada.qty_counted, 0)
        # e é por ela que se pede a reposição
        linha_esgotada.qty_replenish = 6
        reposicao = segundo.action_replenish()
        self.assertEqual(
            sum(reposicao.move_ids.mapped('product_uom_qty')), 6)

    def test_a_title_never_shipped_is_not_on_the_table(self):
        """Planejado não é o mesmo que despachado: só o que foi conta."""
        fantasma = self.env['product.product'].create({
            'name': 'Nunca Despachado', 'type': 'consu', 'is_storable': True})
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        self.env['event.fair.line'].create({
            'fair_id': fair.id, 'product_id': fantasma.id, 'qty_planned': 5})
        dia = fair.day_ids[0]
        dia.action_fill()
        self.assertNotIn(fantasma, dia.line_ids.mapped('product_id'),
                         "Título que não saiu do armazém não está na mesa")

    # --- o mínimo de mesa, decidido pelo gerente --------------------------
    def test_the_minimum_suggests_the_replenishment_by_itself(self):
        """A decisão do gerente viaja até a mesa.

        Ele fixa o mínimo uma vez, na grade ou no modelo. A cada contagem o
        sistema sugere sozinho quanto falta para a mesa voltar àquele
        patamar, e quem está na praça só confirma.
        """
        fair = self._fair(qty=10)
        fair.line_ids.qty_min = 8
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        linha = dia.line_ids
        self.assertEqual(linha.qty_min, 8, "O mínimo é carimbado no dia")
        # nada vendido ainda: a mesa tem 10, acima do mínimo, nada a repor
        self.assertEqual(linha.qty_replenish, 0)
        # vendeu sete, sobraram três: faltam cinco para voltar aos oito
        linha.qty_counted = 3
        self.assertEqual(linha.qty_replenish, 5,
                         "A sugestão é o mínimo menos o que sobrou")
        dia.action_close()
        self.assertEqual(
            sum(dia.replenish_picking_ids.move_ids.mapped('product_uom_qty')),
            5)

    def test_the_suggestion_can_be_typed_over(self):
        """Sugerido, não imposto: quem está na praça sabe do amanhã."""
        fair = self._fair(qty=10)
        fair.line_ids.qty_min = 8
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 3
        self.assertEqual(dia.line_ids.qty_replenish, 5)
        dia.line_ids.qty_replenish = 20   # amanhã vem escola
        self.assertEqual(dia.line_ids.qty_replenish, 20,
                         "O número escrito à mão tem de ficar")
        dia.action_close()
        self.assertEqual(
            sum(dia.replenish_picking_ids.move_ids.mapped('product_uom_qty')),
            20)

    def test_no_minimum_means_no_suggestion(self):
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 1
        self.assertEqual(dia.line_ids.qty_replenish, 0,
                         "Sem mínimo o sistema não sugere nada")

    # --- o retorno lacra os dias ------------------------------------------
    def test_the_return_seals_every_day(self):
        """Feira que voltou não deixa dia aberto para trás.

        Dia aberto na hora do retorno é dia que ninguém fechou: a praça
        esvaziou, a van saiu, e aquela contagem não vai acontecer mais.
        Deixá-lo aberto guarda uma pergunta sem resposta possível e faz a
        lista de fechamentos mentir sobre o que falta fazer.
        """
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        primeiro, segundo = fair.day_ids[0], fair.day_ids[1]
        primeiro.action_fill()
        primeiro.line_ids.qty_counted = 6
        primeiro.action_close()
        self.assertEqual(segundo.state, 'draft')
        self._validate(fair.action_return())
        self.assertEqual(segundo.state, 'closed',
                         "O dia que ninguém fechou tem de fechar no retorno")
        self.assertTrue(segundo.is_sealed)
        self.assertTrue(primeiro.is_sealed,
                        "Lacrar vale para todos, não só para o que ficou aberto")

    def test_a_sealed_day_refuses_a_replenishment(self):
        """Feira que voltou não tem mais mesa para onde mandar."""
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 4
        dia.action_close()
        self._validate(fair.action_return())
        dia.line_ids.qty_replenish = 5
        with self.assertRaises(UserError):
            dia.action_replenish()

    def test_closing_at_return_invents_no_count(self):
        """Dia sem contagem fecha vazio: a diferença é assunto do retorno."""
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        self._validate(fair.action_return())
        self._receber_retorno(fair)
        for dia in fair.day_ids:
            self.assertEqual(dia.state, 'closed')
            self.assertEqual(dia.qty_sold, 0,
                             "Fechar no retorno não inventa venda")
            self.assertFalse(dia.picking_id)
        self.assertEqual(fair.qty_sold, 0)
        self.assertEqual(fair.qty_returned, 10)

    def test_what_is_already_on_the_way_is_not_ordered_twice(self):
        """A equipe não pede reposição todo dia, e o pedido atravessa dias.

        Sai numa noite e chega dois dias depois. Se a contagem seguinte não
        descontar o que está na estrada, ela sugere pedir tudo de novo — e a
        feira recebe em dobro justamente o título que estava faltando.
        """
        fair = self._fair(qty=10)
        fair.line_ids.qty_min = 8
        fair.action_plan()
        self._entregar(fair)
        primeiro = fair.day_ids[0]
        primeiro.action_fill()
        primeiro.line_ids.qty_counted = 2
        self.assertEqual(primeiro.line_ids.qty_replenish, 6)
        primeiro.action_close()
        # a reposição saiu do armazém mas ainda NÃO chegou na praça
        reposicao = primeiro.replenish_picking_ids
        self.assertNotEqual(reposicao.state, 'done')
        self.assertEqual(fair.line_ids.qty_requested, 6,
                         "Seis foram pedidos e ainda não estão na mesa")
        self.assertEqual(fair.line_ids.qty_in_transit, 0,
                         "Mas ainda no armazém: não saíram para a estrada")
        self._validate(reposicao)
        self.assertEqual(fair.line_ids.qty_in_transit, 6,
                         "Despachados: agora sim estão na estrada")
        segundo = fair.day_ids[1]
        segundo.action_fill()
        linha = segundo.line_ids
        self.assertEqual(linha.qty_in_transit, 6,
                         "O dia carimba o que estava a caminho")
        self.assertEqual(linha.qty_expected, 2,
                         "Na mesa há dois: o resto não chegou")
        self.assertEqual(linha.qty_replenish, 0,
                         "Mínimo 8, dois na mesa e seis na estrada: nada a pedir")

    def test_once_it_arrives_it_stops_being_on_the_way(self):
        fair = self._fair(qty=10)
        fair.line_ids.qty_min = 8
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 2
        dia.action_close()
        self.assertEqual(fair.line_ids.qty_requested, 6)
        self._validate(dia.replenish_picking_ids)
        self.assertEqual(fair.line_ids.qty_in_transit, 6)
        self._receber(fair)
        self.assertEqual(fair.line_ids.qty_in_transit, 0,
                         "Chegou: saiu da estrada e entrou na mesa")
        self.assertEqual(fair.qty_on_shelf, 8)

    def test_the_daily_closing_list_shows_what_waits_for_someone(self):
        """A lista de fechamentos abre no que falta fazer, não no histórico.

        Sem filtro ela mostra todo dia de toda feira, inclusive os de feira
        que já voltou meses atrás — e quem abre o menu quer saber o que
        precisa ser contado hoje.
        """
        aberta = self._fair(qty=10)
        aberta.action_plan()
        self._entregar(aberta)
        voltou = self._fair(qty=4)
        voltou.action_plan()
        self._entregar(voltou)
        self._validate(voltou.action_return())

        domain = [('state', '=', 'draft'),
                  ('fair_id.state', 'not in',
                   ('returned', 'settled', 'closed'))]
        esperando = self.env['event.fair.day'].search(domain)
        self.assertTrue(aberta.day_ids & esperando,
                        "Dia de feira em curso espera alguém")
        self.assertFalse(voltou.day_ids & esperando,
                         "Dia de feira que voltou é histórico, sai da frente")

    def test_the_replenishment_says_where_it_came_from(self):
        """Reposição que vira só movimento não avisa ninguém.

        Quem separa no armazém precisa saber que aquela caixa é a reposição
        da contagem de sábado, e quem está na feira precisa saber que o
        pedido foi visto. A transferência carrega o dia, e o histórico da
        feira conta o pedido com o número do movimento para citar.
        """
        fair = self._fair(qty=10)
        fair.line_ids.qty_min = 9
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 3
        antes = len(fair.message_ids)
        dia.action_close()
        reposicao = dia.replenish_picking_ids
        self.assertEqual(reposicao.fair_day_id, dia,
                         "A transferência tem de dizer de que dia veio")
        self.assertGreater(len(fair.message_ids), antes,
                           "O pedido tem de aparecer no histórico da feira")
        aviso = fair.message_ids[0].body
        self.assertIn(reposicao.name, aviso,
                      "O aviso cita o movimento, para a conversa ter número")
        self.assertIn(self.product.display_name, aviso)

    def test_logistics_can_tell_a_replenishment_from_the_first_load(self):
        """A caixa que a feira está esperando não pode parecer remessa comum.

        Quem separa lê a LISTA de transferências, não a ficha de cada uma.
        Reposição que chega depois de a feira acabar não serve para nada, e
        por isso ela tem de se distinguir de longe.
        """
        fair = self._fair(qty=10)
        fair.line_ids.qty_min = 9
        fair.action_plan()
        primeira = fair.action_ship()
        self._validate(primeira)
        self._receber(fair)
        self.assertFalse(primeira.is_fair_replenishment,
                         "A primeira carga não é reposição")
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 2
        dia.action_close()
        reposicao = dia.replenish_picking_ids
        self.assertTrue(reposicao.is_fair_replenishment)
        self.assertIn('replenishment', reposicao.origin.lower(),
                      "A origem tem de dizer que é reposição")
        self.assertIn(fair.code, reposicao.origin,
                      "e de que feira ela é")
        achadas = self.env['stock.picking'].search([
            ('is_fair_replenishment', '=', True),
            ('fair_id', '=', fair.id)])
        self.assertEqual(achadas, reposicao,
                         "O filtro da logística tem de achar só a reposição")

    def test_the_closing_list_opens_on_the_fairs_that_are_out(self):
        """Esta lista junta os dias de TODAS as feiras: sem recorte é um monte.

        O que interessa é a feira que está na rua com livro na mesa. A que já
        voltou é arquivo, e a que ainda não saiu não tem o que contar.
        """
        na_rua = self._fair(qty=10)
        na_rua.action_plan()
        self._entregar(na_rua)
        so_planejada = self._fair(qty=5)
        so_planejada.action_plan()
        ja_voltou = self._fair(qty=4)
        ja_voltou.action_plan()
        self._entregar(ja_voltou)
        self._validate(ja_voltou.action_return())

        em_curso = self.env['event.fair.day'].search(
            [('fair_state', '=', 'shipped')])
        self.assertTrue(na_rua.day_ids & em_curso)
        self.assertFalse(so_planejada.day_ids & em_curso,
                         "Feira que não saiu não tem mesa a contar")
        self.assertFalse(ja_voltou.day_ids & em_curso,
                         "Feira que voltou é arquivo")
        self.assertEqual(na_rua.day_ids[0].fair_state, 'shipped',
                         "A linha tem de dizer em que pé está a feira dela")

    def test_on_the_way_has_a_door(self):
        """O número "A caminho" tem de abrir a transferência.

        Sem isso ele diz que falta chegar e não diz por onde. Quem está na
        praça quer a resposta seguinte: saiu? quando chega? E ela está no
        movimento, não neste número.
        """
        fair = self._fair(qty=10)
        fair.line_ids.qty_min = 9
        fair.action_plan()
        self._entregar(fair)
        dia = fair.day_ids[0]
        self.assertEqual(dia.in_transit_count, 0,
                         "Tudo chegou: nada na estrada")
        dia.action_fill()
        dia.line_ids.qty_counted = 2
        dia.action_close()
        reposicao = dia.replenish_picking_ids
        segundo = fair.day_ids[1]
        self.assertEqual(segundo.in_transit_count, 1,
                         "A reposição que não chegou aparece no dia seguinte")
        self.assertEqual(segundo.in_transit_picking_ids, reposicao)
        acao = segundo.action_view_in_transit()
        self.assertEqual(
            self.env['stock.picking'].search(acao['domain']), reposicao,
            "O botão tem de abrir exatamente a carga que está vindo")
        self._validate(reposicao)
        self.assertEqual(segundo.in_transit_count, 0,
                         "Chegou: o botão some")

    def test_the_return_counts_the_table_after_closing_the_days(self):
        """Fechar os dias PRIMEIRO, contar a mesa DEPOIS.

        Ao contrário, o retorno nasce pedindo o saldo de antes: os
        fechamentos que faltavam vendem no mesmo clique, o estoque some da
        localização e a transferência fica "Não disponível" pedindo cinco
        onde restaram três. Aconteceu na E00011 do dev, e as vendas tinham o
        mesmo carimbo de hora do retorno.
        """
        fair = self._fair(qty=10)
        fair.action_plan()
        self._entregar(fair)
        # um dia contado mas NÃO fechado: seis na mesa, quatro vendidos
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = 6
        self.assertEqual(dia.state, 'draft')
        retorno = fair.action_return()
        self.assertEqual(dia.state, 'closed',
                         "O retorno fecha o dia que ficou aberto")
        self.assertEqual(fair.qty_sold, 4)
        self.assertEqual(
            sum(retorno.move_ids.mapped('product_uom_qty')), 6,
            "O retorno pede SEIS, que é o que sobrou depois do fechamento")
        retorno.action_assign()
        self.assertEqual(retorno.state, 'assigned',
                         "e por isso a transferência fica disponível")
        for move in retorno.move_ids:
            self.assertEqual(move.quantity, 6,
                             "com tudo reservado, sem 'Não disponível'")

    def test_the_transfer_says_which_fair_it_belongs_to(self):
        """A conversa da equipe acontece no histórico da transferência.

        Ali o Odoo só diz "Transferir criado". Quem recebe a caixa precisa
        saber de que feira ela é antes de responder qualquer coisa, e o
        código sozinho não diz nada a quem está no armazém.
        """
        fair = self._fair(qty=10)
        fair.action_plan()
        picking = fair.action_ship()
        corpos = ' '.join(picking.message_ids.mapped('body'))
        self.assertIn(fair.name, corpos,
                      "O histórico da transferência tem de nomear a feira")
        self.assertIn(fair.code, corpos)

    def test_pressing_dispatch_twice_does_not_ship_twice(self):
        """O segundo clique não pode mandar a grade de novo.

        O "planejado que ainda não foi" precisa descontar o que está A
        CAMINHO, e não só o que já chegou. Descontando apenas o concluído, o
        segundo Despachar antes de o armazém validar a primeira carga nasce
        com a grade inteira, e a feira recebe em dobro.
        """
        fair = self._fair(qty=10)
        fair.action_plan()
        primeira = fair.action_ship()
        self.assertEqual(
            sum(primeira.move_ids.mapped('product_uom_qty')), 10)
        self.assertNotEqual(primeira.state, 'done')
        with self.assertRaises(UserError):
            fair.action_ship()
        self.assertEqual(
            len(fair.picking_ids.filtered(
                lambda p: p.fair_operation == 'shipment')), 1,
            "Continua havendo UMA carga a caminho")
        # e a reposição de verdade continua funcionando
        fair.line_ids.qty_planned = 14
        segunda = fair.action_ship()
        self.assertEqual(
            sum(segunda.move_ids.mapped('product_uom_qty')), 4,
            "A reposição manda só a diferença, mesmo com a primeira na estrada")

    # --- quem garante que chegou -------------------------------------------
    def test_the_warehouse_dispatching_is_not_the_fair_receiving(self):
        """A pergunta dele: o depósito despacha, mas quem garante que chegou?

        Numa perna só, o instante em que o depósito valida é o instante em
        que o sistema jura que o livro está na mesa em Santos. Ele pode estar
        na estrada, ou em lugar nenhum. Quem garante é quem está na praça.
        """
        fair = self._fair(qty=10)
        fair.action_plan()
        saida = fair.action_ship()
        self.assertEqual(saida.fair_operation, 'shipment')
        entrada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt')
        self.assertTrue(entrada, "A ida nasce com as DUAS pernas")
        self.assertEqual(entrada.state, 'waiting',
                         "A entrada espera a saída")

        self._validate(saida)
        self.assertEqual(fair.qty_sent, 0,
                         "Despachar não é chegar")
        self.assertEqual(fair.qty_on_shelf, 0,
                         "A mesa continua vazia até alguém conferir na praça")
        self.assertEqual(fair.line_ids.qty_in_transit, 10,
                         "Os dez estão em trânsito")
        quant = self.env['stock.quant'].search([
            ('location_id', '=', fair.stock_location_id.id),
            ('product_id', '=', self.product.id)])
        self.assertEqual(sum(quant.mapped('quantity')), 0,
                         "E não na localização da feira")

        self._receber(fair)
        self.assertEqual(fair.qty_sent, 10, "Agora sim: chegou")
        self.assertEqual(fair.qty_on_shelf, 10)
        self.assertEqual(fair.line_ids.qty_in_transit, 0)

    def test_a_load_that_arrives_short_stays_visible(self):
        """Saíram dez, chegaram sete: os três não se dissolvem.

        Eles não estão no armazém nem na mesa. Ficam no trânsito, com uma
        entrada pendente atrás deles — que é a pergunta "onde estão os três?"
        em forma de documento.
        """
        fair = self._fair(qty=10)
        fair.action_plan()
        self._validate(fair.action_ship())
        entrada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt' and p.state != 'done')
        entrada.action_assign()
        for move in entrada.move_ids:
            move.quantity = 7
            move.picked = True
        # COM pedido pendente: os três que faltam continuam cobrados
        res = entrada.button_validate()
        if isinstance(res, dict) and res.get('res_model') == \
                'stock.backorder.confirmation':
            self.env[res['res_model']].with_context(
                **res['context']).create({}).process()
        self.assertEqual(fair.qty_sent, 7, "Chegaram sete")
        self.assertEqual(fair.qty_on_shelf, 7)
        # Os três não se dissolvem: ficam no TRÂNSITO, que é a verdade
        # física. Não estão no armazém (saíram) nem na mesa (não chegaram),
        # e é essa a pergunta que o módulo passa a saber fazer.
        transito = fair._get_transit_location()
        parados = self.env['stock.quant'].search([
            ('location_id', '=', transito.id),
            ('product_id', '=', self.product.id)])
        self.assertEqual(sum(parados.mapped('quantity')), 3,
                         "Os três que faltam estão parados no trânsito")
        armazem = self.env['stock.quant'].search([
            ('location_id', '=', self.stock_location.id),
            ('product_id', '=', self.product.id)])
        self.assertEqual(sum(armazem.mapped('quantity')), 90,
                         "e não voltaram para o armazém sozinhos")
