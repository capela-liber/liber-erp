# -*- coding: utf-8 -*-
"""O evento: número, calendário, grade e as transições da fase 1.

Defende três regras: a feira nasce com número E próprio (série separada da
venda), o período do evento não pode terminar antes de começar, e planejar
uma feira sem grade não é planejar coisa nenhuma.
"""
from datetime import date, timedelta

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs')
class TestEventFair(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': 'O Livro da Feira',
            'type': 'consu',
            'is_storable': True,
            'list_price': 60.0,
        })
        cls.today = date(2026, 9, 20)

    def _fair(self, **kwargs):
        vals = {
            'name': 'Feira Literária de Paraty',
            'date_start': self.today,
            'date_end': self.today + timedelta(days=2),
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id, 'qty_planned': 10,
            })],
        }
        vals.update(kwargs)
        return self.env['event.fair'].create(vals)

    # --- caminho feliz ---------------------------------------------------
    def test_event_gets_its_own_reference(self):
        """O evento nasce EV/ANO/NNNNN, em série própria.

        Não é E00001: "E" com cinco dígitos se confundia com B0000 e C0000,
        que são documentos de PEDIDO. Evento não é pedido -- é o disparador do
        que vem depois (remessa, caixa, retorno, comissão), como a CO da
        consignação. A forma com barra e ano diz isso de longe, e é a mesma
        que vai para o analítico.
        """
        import re
        fair = self._fair()
        self.assertRegex(
            fair.code, r'^EV/\d{4}/\d{5}$',
            "A referência do evento devia ser EV/ANO/NNNNN, veio %s"
            % fair.code)
        self.assertIn(str(fair.date_start.year)[:2], fair.code[:8])
        self.assertIn(fair.code, fair.display_name)
        self.assertTrue(re.match(r'^EV/', fair.code))

    def test_two_fairs_get_different_references(self):
        primeira = self._fair()
        segunda = self._fair(name='Bienal do Livro')
        self.assertNotEqual(primeira.code, segunda.code)

    def test_plan_builds_location_and_days(self):
        """Planejar cria a localização da feira e um registro por dia."""
        fair = self._fair()
        fair.action_plan()
        self.assertEqual(fair.state, 'planned')
        self.assertTrue(fair.stock_location_id,
                        "Planejar devia ter criado a localização da feira")
        self.assertEqual(fair.stock_location_id.name, fair.code)
        # 20, 21 e 22 de setembro: três dias, três fechamentos.
        self.assertEqual(fair.day_count, 3,
                         "Feira de três dias devia ter três fechamentos")
        self.assertEqual(sorted(fair.day_ids.mapped('date')),
                         [self.today, self.today + timedelta(days=1),
                          self.today + timedelta(days=2)])

    def test_plan_twice_does_not_duplicate_days(self):
        """Replanejar não duplica o fechamento diário."""
        fair = self._fair()
        fair.action_plan()
        fair.action_plan()
        self.assertEqual(fair.day_count, 3)

    # --- borda ------------------------------------------------------------
    def test_one_day_fair_has_one_day(self):
        """Lançamento de uma tarde é uma feira de um dia só."""
        fair = self._fair(date_end=self.today)
        fair.action_plan()
        self.assertEqual(fair.day_count, 1)

    # --- erro -------------------------------------------------------------
    def test_fair_cannot_end_before_it_starts(self):
        with self.assertRaises(UserError):
            self._fair(date_end=self.today - timedelta(days=1))

    def test_plan_without_a_grid_is_refused(self):
        """Planejar sem grade não é planejar: não há o que mandar."""
        fair = self._fair(line_ids=[])
        with self.assertRaises(UserError):
            fair.action_plan()

    def test_a_title_appears_once_in_the_grid(self):
        with self.assertRaises(Exception):
            fair = self._fair()
            fair.write({'line_ids': [(0, 0, {
                'product_id': self.product.id, 'qty_planned': 3})]})
            fair.flush_recordset()

    def test_a_returned_fair_leaves_the_open_list(self):
        """Encerrada é retornada: a feira acaba quando a mercadoria volta.

        Acertado e Encerrado são degraus do faturamento, que ainda não
        existe. Filtrar só por "encerrado" fazia o filtro não filtrar nada, e
        a lista das feiras em aberto mostrava para sempre a que já voltou.
        """
        fair = self._fair()
        fair.action_plan()
        aberto = [('state', 'not in', ('returned', 'settled', 'closed'))]
        self.assertIn(fair, self.env['event.fair'].search(aberto))
        fair.action_ship()
        fair.state = 'returned'
        self.assertNotIn(fair, self.env['event.fair'].search(aberto),
                         "Feira que voltou não é feira em aberto")
