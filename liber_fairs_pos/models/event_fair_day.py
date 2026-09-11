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
import pytz
from datetime import datetime, time

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

    # ACUMULADO, e não o dia. A janela do dia deixava venda de fora: sessão
    # aberta na véspera para testar o balcão, venda depois da meia-noite,
    # feira cujo primeiro dia começou antes da data cadastrada. O número
    # sumia, e a coluna dizia zero numa mesa que tinha vendido.
    #
    # Acumulado também é o que CASA COM O ESPERADO: o esperado já desconta
    # toda a venda do evento, não a de um dia. Ler os dois lado a lado só
    # fecha se falarem do mesmo período.
    qty_pos = fields.Float(
        string='At the register', digits='Product Unit',
        compute='_compute_qty_pos',
        help="Copies of this title the fair's registers have sold SO FAR, "
             "from the start of the event through this day. It is the number "
             "that pairs with Expected, which also nets out every sale. The "
             "difference against your count is what nobody sees any other "
             "way.")
    qty_pos_day = fields.Float(
        string='Sold today', digits='Product Unit',
        compute='_compute_qty_pos',
        help="Only what was sold on this day, for whoever wants to know how "
             "Saturday went.")

    @api.depends('product_id', 'day_id.date', 'day_id.fair_id')
    def _compute_qty_pos(self):
        acumulado, do_dia = {}, {}
        for line in self:
            line.qty_pos = line.qty_pos_day = 0.0
            dia = line.day_id
            if not (dia.fair_id and dia.date):
                continue
            chave = (dia.fair_id.id, dia.date)
            if chave not in acumulado:
                acumulado[chave] = self._vendas_do_dia(dia, acumulado=True)
                do_dia[chave] = self._vendas_do_dia(dia)
            line.qty_pos = acumulado[chave].get(line.product_id.id, 0.0)
            line.qty_pos_day = do_dia[chave].get(line.product_id.id, 0.0)

    @api.model
    def _bordas_do_dia(self, data):
        """A meia-noite e o fim do dia DAQUELE fuso, em UTC."""
        fuso = pytz.timezone(self.env.user.tz or 'UTC')
        abertura = fuso.localize(datetime.combine(data, time.min))
        fechamento = fuso.localize(datetime.combine(data, time.max))
        return (abertura.astimezone(pytz.UTC).replace(tzinfo=None),
                fechamento.astimezone(pytz.UTC).replace(tzinfo=None))

    @api.model
    def _vendas_do_dia(self, dia, acumulado=False):
        """{produto: quantidade} do que os caixas da feira venderam no dia.

        Lê pelo PEDIDO, e não pelo movimento de estoque: o pedido tem a data e
        a hora da venda, que é o que amarra a venda ao dia. Devolução no
        balcão entra com sinal negativo, porque é assim que ela é lançada.
        """
        configs = dia.fair_id.with_context(active_test=False).pos_config_ids
        if not configs:
            return {}
        # O DIA É O DIA DE QUEM VENDE, e o banco guarda UTC. Comparar a data
        # da feira com o carimbo cru jogava a venda das 21h para o dia
        # seguinte -- e feira vende de noite. As bordas se convertem do fuso
        # de quem está olhando.
        inicio, fim = self._bordas_do_dia(dia.date)
        dominio = [('order_id.config_id', 'in', configs.ids),
                   ('order_id.state', '!=', 'cancel'),
                   ('order_id.date_order', '<=', fim)]
        if not acumulado:
            # Sem piso, tudo o que o evento já vendeu entra. Com piso, só o
            # dia -- e o dia é a exceção, não a regra.
            dominio.append(('order_id.date_order', '>=', inicio))
        agrupado = self.env['pos.order.line'].sudo()._read_group(
            dominio, ['product_id'], ['qty:sum'])
        return {produto.id: quantidade for produto, quantidade in agrupado}
