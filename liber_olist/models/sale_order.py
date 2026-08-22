# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleOrder(models.Model):
    """Ao confirmar o pedido, a nota do Olist vai junto para a transferência.

    Este é o momento certo do carimbo, e o `create` do picking não era: ali o
    `sale_id` ainda não está preenchido (é related de `group_id`, resolvido no
    flush seguinte), então o gancho encontrava sempre transferência sem pedido.

    O caso existe mesmo com o import confirmando na hora (22/08/2026):
    devolução e entrega refeita criam picking com a fatura já antiga.
    """
    _inherit = 'sale.order'

    # O caminho de volta: é por ele que a lista de entregas filtra "Do Olist"
    # — a fila de embalagem do marketplace, separada do resto da expedição.
    olist_order_ids = fields.One2many('olist.order', 'sale_order_id',
                                      string="Pedidos do Olist")

    def action_confirm(self):
        resultado = super().action_confirm()
        self.picking_ids._liber_olist_carimbar_nota()
        return resultado
