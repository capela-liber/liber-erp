# -*- coding: utf-8 -*-
"""A agenda: prazo, atraso e o tempo que a Amazon concede."""

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import AmazonVendorCase, amazon_item, amazon_order


def _janela(inicio_dias, fim_dias, base=None):
    """Monta um deliveryWindow relativo a hoje, no formato da SP-API."""
    base = base or fields.Datetime.now()
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return "%s--%s" % ((base + timedelta(days=inicio_dias)).strftime(fmt),
                       (base + timedelta(days=fim_dias)).strftime(fmt))


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonSchedule(AmazonVendorCase):

    def _com_prazo(self, name, inicio, fim, state='Acknowledged'):
        """Pedido feito hoje, com a janela de entrega em dias a partir de hoje.

        A data do pedido acompanha: o prazo concedido se mede do pedido até o
        fim da janela, e deixar a data fixa do fixture mediria outra coisa.
        """
        agora = fields.Datetime.now()
        self._sync([amazon_order(
            name, [amazon_item('1', '9786551590016')], state=state,
            order_date=agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            window=_janela(inicio, fim, base=agora))])
        return self._order(name)

    # ------------------------------------------------------- caminho feliz

    def test_days_left_counts_down(self):
        ordem = self._com_prazo('BR-4000', 3, 10)
        self.assertEqual(ordem.days_to_deadline, 10)
        self.assertFalse(ordem.is_late)

    def test_overdue_is_negative_and_flagged(self):
        ordem = self._com_prazo('BR-4001', -20, -5)
        self.assertEqual(ordem.days_to_deadline, -5)
        self.assertTrue(ordem.is_late)

    def test_days_granted_is_the_window_amazon_gave(self):
        """
        Gravado porque não muda: é fato sobre o pedido, não sobre hoje. Por
        isso pode ser agrupado e somado sem envelhecer.
        """
        ordem = self._com_prazo('BR-4002', 5, 25)
        # do pedido (hoje, no fixture) até o fim da janela
        self.assertEqual(ordem.lead_time_days, 25)

    # ----------------------------------------------------------- edge cases

    def test_closed_order_is_never_late(self):
        """
        Pedido que a Amazon fechou já foi entregue ou cancelado. Contá-lo como
        atrasado encheria a tela de dívida que não existe — e esconderia os
        treze que importam.
        """
        ordem = self._com_prazo('BR-4010', -30, -10, state='Closed')
        self.assertFalse(ordem.is_late)
        self.assertEqual(ordem.days_to_deadline, 0)

    def test_order_without_window_has_no_deadline(self):
        self._sync([amazon_order('BR-4011', [amazon_item('1', '9786551590016')],
                                 window=None)])
        ordem = self._order('BR-4011')
        self.assertFalse(ordem.is_late)
        self.assertEqual(ordem.days_to_deadline, 0)
        self.assertEqual(ordem.lead_time_days, 0)

    def test_deadline_today_is_not_late_yet(self):
        ordem = self._com_prazo('BR-4012', -5, 0)
        self.assertEqual(ordem.days_to_deadline, 0)
        self.assertFalse(ordem.is_late, "vence hoje ainda dá para entregar")

    # -------------------------------------------------------------- filtro

    def test_overdue_filter_finds_them_in_the_database(self):
        """
        `is_late` não é gravado — muda sozinho à meia-noite. O filtro precisa
        virar condição sobre `delivery_end`, que é coluna de verdade, senão o
        Odoo carregaria todos os pedidos para descobrir quais estão atrasados.
        """
        atrasado = self._com_prazo('BR-4020', -30, -3)
        em_dia = self._com_prazo('BR-4021', 2, 15)
        fechado = self._com_prazo('BR-4022', -40, -20, state='Closed')

        achados = self.env['liber.amazon.order'].search([('is_late', '=', True)])
        self.assertIn(atrasado, achados)
        self.assertNotIn(em_dia, achados)
        self.assertNotIn(fechado, achados)

        no_prazo = self.env['liber.amazon.order'].search([('is_late', '=', False)])
        self.assertIn(em_dia, no_prazo)
        self.assertIn(fechado, no_prazo)
        self.assertNotIn(atrasado, no_prazo)

    def test_grouping_by_deadline_month_works(self):
        """O relatório agrupa por mês de prazo; se o campo não agrupasse,
        a tela de pivô viria vazia."""
        self._com_prazo('BR-4030', 3, 10)
        grupos = self.env['liber.amazon.order']._read_group(
            [('delivery_end', '!=', False)],
            ['delivery_end:month'], ['__count'])
        self.assertTrue(grupos)
