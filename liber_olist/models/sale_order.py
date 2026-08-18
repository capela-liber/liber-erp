# -*- coding: utf-8 -*-

from odoo import models


class SaleOrder(models.Model):
    """Ao confirmar o pedido, a nota do Olist vai junto para a transferência.

    Este é o momento certo do carimbo, e o `create` do picking não era: ali o
    `sale_id` ainda não está preenchido (é related de `group_id`, resolvido no
    flush seguinte), então o gancho encontrava sempre transferência sem pedido.

    E é o momento NORMAL: sem corte de estoque configurado, o pedido do Olist
    entra em rascunho com a fatura já pronta, e a entrega só nasce quando a
    logística confirma o S — horas depois.
    """
    _inherit = 'sale.order'

    def action_confirm(self):
        resultado = super().action_confirm()
        self.picking_ids._liber_olist_carimbar_nota()
        return resultado
