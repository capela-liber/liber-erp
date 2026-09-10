# -*- coding: utf-8 -*-
"""O que o CAIXA vendeu naquele dia, na tela de quem conta a mesa.

O fechamento diário pergunta uma coisa só: quantos exemplares sobraram. O
"Vendido" dele é subtração -- esperado menos contado --, e por isso nasce
zero: a contagem vem pré-preenchida igual ao esperado, e quem conta corrige
para baixo.

Com o balcão do PDV registrando venda na hora, existe um segundo número, e
ele é o mais interessante dos dois: o que o caixa REGISTROU. A diferença
entre os dois é o que ninguém vê de outro jeito -- venda que não passou pelo
caixa, exemplar que sumiu da mesa.

Este módulo NÃO fecha o dia quando o caixa fecha, de propósito. Fechar o dia
é dizer "contei a mesa"; se quem fecha é a máquina, o sistema estaria
inventando uma contagem que ninguém fez -- e é justamente essa contagem que
pega o que o caixa não viu.
"""
from odoo import api, fields, models


class EventFairDay(models.Model):
    _inherit = 'event.fair.day'

    pos_qty = fields.Float(
        string='Sold at the register', digits='Product Unit',
        compute='_compute_pos_qty')

    @api.depends('date', 'fair_id')
    def _compute_pos_qty(self):
        for day in self:
            day.pos_qty = sum(day.line_ids.mapped('qty_pos'))


class EventFairDayLine(models.Model):
    _inherit = 'event.fair.day.line'

    qty_pos = fields.Float(
        string='At the register', digits='Product Unit',
        compute='_compute_qty_pos',
        help="Copies this title sold at the fair's registers on this day. "
             "The difference against your count is what nobody sees any "
             "other way.")

    @api.depends('product_id', 'day_id.date', 'day_id.fair_id')
    def _compute_qty_pos(self):
        por_dia = {}
        for line in self:
            line.qty_pos = 0.0
            dia = line.day_id
            chave = (dia.fair_id.id, dia.date)
            if not (dia.fair_id and dia.date):
                continue
            if chave not in por_dia:
                por_dia[chave] = self._vendas_do_dia(dia)
            line.qty_pos = por_dia[chave].get(line.product_id.id, 0.0)

    @api.model
    def _vendas_do_dia(self, dia):
        """{produto: quantidade} do que os caixas da feira venderam no dia.

        Lê pelo PEDIDO, e não pelo movimento de estoque: o pedido tem a data e
        a hora da venda, que é o que amarra a venda ao dia. Devolução no
        balcão entra com sinal negativo, porque é assim que ela é lançada.
        """
        configs = dia.fair_id.with_context(active_test=False).pos_config_ids
        if not configs:
            return {}
        agrupado = self.env['pos.order.line'].sudo()._read_group(
            [('order_id.config_id', 'in', configs.ids),
             ('order_id.state', '!=', 'cancel'),
             ('order_id.date_order', '>=', f'{dia.date} 00:00:00'),
             ('order_id.date_order', '<=', f'{dia.date} 23:59:59')],
            ['product_id'], ['qty:sum'])
        return {produto.id: quantidade for produto, quantidade in agrupado}
