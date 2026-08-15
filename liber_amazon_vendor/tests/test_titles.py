# -*- coding: utf-8 -*-
"""Análise por título: onde cada livro parou, e quanto durou o ciclo."""

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import AmazonVendorCase, amazon_item, amazon_order


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonTitles(AmazonVendorCase):

    # ------------------------------------------------- onde o título parou

    def test_line_without_product_is_not_served(self):
        self._sync([amazon_order('BR-5000', [
            amazon_item('1', '9788500000009', qty=78)])])
        linha = self._order('BR-5000').line_ids
        self.assertEqual(linha.fulfilment_state, 'no_product')

    def test_line_with_product_but_no_quotation_is_pending(self):
        """
        Separar "sem produto" de "sem cotação" importa: são problemas de gente
        diferente. O primeiro é do cadastro; o segundo é de quem opera.
        """
        self._sync([amazon_order('BR-5001', [
            amazon_item('1', '9786551590016')])])
        self.assertEqual(self._order('BR-5001').line_ids.fulfilment_state,
                         'pending')

    def test_line_becomes_quoted_when_the_quotation_is_made(self):
        self._sync([amazon_order('BR-5002', [
            amazon_item('1', '9786551590016')])])
        ordem = self._order('BR-5002')
        ordem.action_create_quotation()
        self.assertEqual(ordem.line_ids.fulfilment_state, 'quoted')

    def test_the_ignored_line_stays_unserved_after_the_quotation(self):
        """
        A linha que ficou de fora não vira 'quoted' só porque o pedido virou
        cotação — senão o relatório diria que o título foi atendido quando
        ninguém o entregou.
        """
        self._sync([amazon_order('BR-5003', [
            amazon_item('1', '9786551590016'),
            amazon_item('2', '9788500000009'),
        ])])
        ordem = self._order('BR-5003')
        ordem.action_create_quotation()

        orfa = ordem.line_ids.filtered(lambda l: l.isbn == '9788500000009')
        self.assertEqual(orfa.fulfilment_state, 'no_product')

    # ---------------------------------------------------- tempo de ciclo

    def test_days_to_close_measures_order_to_closure(self):
        agora = fields.Datetime.now()
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        self._sync([amazon_order(
            'BR-5010', [amazon_item('1', '9786551590016')], state='Closed',
            order_date=(agora - timedelta(days=20)).strftime(fmt))])
        ordem = self._order('BR-5010')
        # o fixture usa a mesma data para pedido e mudança de estado
        self.assertEqual(ordem.days_to_close, 0)

        ordem.invalidate_recordset()
        self.env['liber.amazon.order'].browse(ordem.id).write({})
        # agora com o fechamento 18 dias depois do pedido
        self._sync([amazon_order(
            'BR-5011', [amazon_item('1', '9786551590016')], state='Closed',
            order_date=(agora - timedelta(days=18)).strftime(fmt))])
        outro = self._order('BR-5011')
        outro.state_changed_date = agora
        self.assertEqual(outro.days_to_close, 18)

    def test_open_order_has_no_cycle_to_measure(self):
        """
        Zero enquanto está aberto — e por isso o relatório oferece o filtro
        'ciclo concluído': sem ele, os abertos entram como zero e diluem a
        média para baixo.
        """
        self._sync([amazon_order('BR-5020', [
            amazon_item('1', '9786551590016')], state='Acknowledged')])
        self.assertEqual(self._order('BR-5020').days_to_close, 0)

    def test_line_mirrors_the_order_for_grouping(self):
        """
        O pivô agrupa por mês e por destino, e esses campos vivem no pedido.
        Relacionado sem `store` não entra em agrupamento — se algum dia
        alguém tirar o store, este teste cai.
        """
        self._sync([amazon_order('BR-5030', [
            amazon_item('1', '9786551590016')])])
        linha = self._order('BR-5030').line_ids
        self.assertEqual(linha.ship_to_party, 'CD_CAJAMAR')
        self.assertTrue(linha.order_date)
        self.assertEqual(linha.amazon_state, 'Acknowledged')

    # ------------------------------------------------------------- pivô

    def test_pivot_can_group_by_title_and_fulfilment(self):
        """Se os campos não fossem gravados, a tela de pivô viria vazia."""
        self._sync([amazon_order('BR-5040', [
            amazon_item('1', '9786551590016', qty=10),
            amazon_item('2', '9788500000009', qty=5),
        ])])
        grupos = self.env['liber.amazon.order.line']._read_group(
            [('order_id.name', '=', 'BR-5040')],
            ['fulfilment_state'], ['quantity:sum'])
        por_estado = dict(grupos)
        self.assertAlmostEqual(por_estado['pending'], 10, places=2)
        self.assertAlmostEqual(por_estado['no_product'], 5, places=2)

    def test_subtotal_is_stored_so_it_can_be_a_measure(self):
        self._sync([amazon_order('BR-5050', [
            amazon_item('1', '9786551590016', qty=10, net_cost='45.50')])])
        grupos = self.env['liber.amazon.order.line']._read_group(
            [('order_id.name', '=', 'BR-5050')], [], ['subtotal:sum'])
        self.assertAlmostEqual(grupos[0][0], 455.0, places=2)

    # ------------------------------------------- ainda dá, ou já era?

    def test_unserved_on_an_open_order_is_still_possible(self):
        """Enquanto a Amazon não fecha, cadastrar o título ainda resolve."""
        self._sync([amazon_order('BR-6000', [
            amazon_item('1', '9788500000009')], state='Acknowledged')])
        self.assertEqual(self._order('BR-6000').line_ids.outcome, 'open')

    def test_unserved_on_a_closed_order_is_a_closed_window(self):
        """
        Depois que a Amazon fecha, aquele título naquele pedido não vai mais a
        lugar nenhum. É a resposta para "não foi atendido e não será mais".
        """
        self._sync([amazon_order('BR-6001', [
            amazon_item('1', '9788500000009')], state='Closed')])
        self.assertEqual(self._order('BR-6001').line_ids.outcome, 'missed')

    def test_quoted_is_served_even_on_a_closed_order(self):
        self._sync([amazon_order('BR-6002', [
            amazon_item('1', '9786551590016')])])
        ordem = self._order('BR-6002')
        ordem.action_create_quotation()
        self._sync([amazon_order('BR-6002', [
            amazon_item('1', '9786551590016')], state='Closed')])
        self.assertEqual(self._order('BR-6002').line_ids.outcome, 'served')

    def test_the_window_closes_when_amazon_closes_the_order(self):
        """
        O desfecho acompanha o estado: um pedido que era recuperável ontem
        deixa de ser quando a releitura traz o fechamento.
        """
        self._sync([amazon_order('BR-6003', [
            amazon_item('1', '9786551590016')], state='Acknowledged')])
        self.assertEqual(self._order('BR-6003').line_ids.outcome, 'open')

        self._sync([amazon_order('BR-6003', [
            amazon_item('1', '9786551590016')], state='Closed')])
        self.assertEqual(self._order('BR-6003').line_ids.outcome, 'missed')

    def test_cause_and_deadline_are_separate_axes(self):
        """
        Juntar os dois num campo só perderia um deles: o mesmo 'sem cadastro'
        é recuperável num pedido aberto e perdido num fechado.
        """
        self._sync([
            amazon_order('BR-6010', [amazon_item('1', '9788500000009')],
                         state='Acknowledged'),
            amazon_order('BR-6011', [amazon_item('1', '9788500000009')],
                         state='Closed'),
        ])
        aberto = self._order('BR-6010').line_ids
        fechado = self._order('BR-6011').line_ids

        self.assertEqual(aberto.fulfilment_state, fechado.fulfilment_state)
        self.assertNotEqual(aberto.outcome, fechado.outcome)

    def test_pivot_groups_by_outcome(self):
        self._sync([
            amazon_order('BR-6020', [amazon_item('1', '9788500000009', qty=7)],
                         state='Closed'),
            amazon_order('BR-6021', [amazon_item('1', '9788500000009', qty=3)],
                         state='New'),
        ])
        grupos = dict(self.env['liber.amazon.order.line']._read_group(
            [('order_id.name', 'in', ['BR-6020', 'BR-6021'])],
            ['outcome'], ['quantity:sum']))
        self.assertAlmostEqual(grupos['missed'], 7, places=2)
        self.assertAlmostEqual(grupos['open'], 3, places=2)

    # ------------------------------------------------------ rótulo curto

    def test_long_title_is_cut_with_an_ellipsis(self):
        longo = self.env['product.product'].create({
            'name': 'Memórias Póstumas de Brás Cubas seguidas de Quincas Borba',
            'type': 'consu', 'barcode': '9786551590900',
        })
        self._sync([amazon_order('BR-7000', [
            amazon_item('1', '9786551590900')])])
        rotulo = self._order('BR-7000').line_ids.short_label

        self.assertTrue(rotulo.startswith('9786551590900 · '))
        self.assertTrue(rotulo.endswith('…'))
        self.assertLess(len(rotulo), len(longo.name))

    def test_short_title_is_left_alone(self):
        self._sync([amazon_order('BR-7001', [
            amazon_item('1', '9786551590085')])])
        rotulo = self._order('BR-7001').line_ids.short_label
        self.assertEqual(rotulo, '9786551590085 · O Ateneu')
        self.assertNotIn('…', rotulo)

    def test_titles_sharing_a_prefix_do_not_collapse(self):
        """
        O motivo do ISBN na frente. Sem ele, dois volumes de uma coleção
        cortados no mesmo ponto virariam o MESMO rótulo, o pivô somaria os
        dois numa linha só, e o número sairia errado sem nada denunciando.
        """
        base = 'História da Literatura Brasileira, volume '
        for sufixo, barcode in (('I', '9786551590901'), ('II', '9786551590902')):
            self.env['product.product'].create({
                'name': base + sufixo, 'type': 'consu', 'barcode': barcode})
        self._sync([amazon_order('BR-7002', [
            amazon_item('1', '9786551590901'),
            amazon_item('2', '9786551590902'),
        ])])
        rotulos = self._order('BR-7002').line_ids.mapped('short_label')
        self.assertEqual(len(set(rotulos)), 2, "os dois volumes viraram um só")

    def test_line_without_product_still_gets_a_label(self):
        self._sync([amazon_order('BR-7003', [
            amazon_item('1', '9788500000009')])])
        rotulo = self._order('BR-7003').line_ids.short_label
        self.assertIn('9788500000009', rotulo)

    def test_pivot_can_group_by_the_short_label(self):
        self._sync([amazon_order('BR-7004', [
            amazon_item('1', '9786551590016', qty=4)])])
        grupos = self.env['liber.amazon.order.line']._read_group(
            [('order_id.name', '=', 'BR-7004')],
            ['short_label'], ['quantity:sum'])
        self.assertAlmostEqual(dict(grupos)['9786551590016 · Memórias Póstumas de Brás Cubas'],
                               4, places=2)
