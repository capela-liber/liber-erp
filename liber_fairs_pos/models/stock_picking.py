# -*- coding: utf-8 -*-
"""O movimento do PDV nasce carimbado como venda da feira.

Este é o ponto inteiro da ponte. Sem o carimbo, a saída do caixa seria uma
transferência qualquer: a feira não a veria, `qty_on_shelf` continuaria
dizendo dez com seis na mesa, e o fechamento diário -- que desconta a
diferença entre o esperado e o contado -- lançaria a MESMA venda outra vez.
O estoque da mesa terminaria negativo, e o relatório da feira contaria o
dobro do que se vendeu.

O carimbo vem do tipo de operação, e não do pedido do PDV, de propósito: o
Odoo cria a transferência do balcão em mais de um caminho (venda, devolução,
sessão fechada em lote), e todos passam pelo tipo.
"""
from odoo import api, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model_create_multi
    def create(self, vals_list):
        tipos = self.env['stock.picking.type'].browse({
            vals['picking_type_id'] for vals in vals_list
            if vals.get('picking_type_id')})
        feira_por_tipo = {t.id: t.fair_id.id for t in tipos if t.fair_id}
        for vals in vals_list:
            feira = feira_por_tipo.get(vals.get('picking_type_id'))
            if feira and not vals.get('fair_id'):
                vals['fair_id'] = feira
                vals['fair_operation'] = 'sale'
        return super().create(vals_list)
