# -*- coding: utf-8 -*-
"""A operação do caixa pertence a UMA feira.

O tipo de operação do PDV é criado por feira, e não por empresa como os
outros da casa, porque é ele que carrega a localização de origem: é o campo
que o Ponto de Venda lê para saber de onde tirar o livro. Uma operação por
empresa serviria a uma feira só de cada vez, e duas feiras simultâneas -- que
existem -- passariam a vender do mesmo lugar.
"""
from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    # A MARCA NÃO PODE DEPENDER DA FEIRA EXISTIR. `fair_id` vira nulo quando
    # alguém apaga a feira (é `set null` de propósito, para o histórico não
    # ir junto), e aí o tipo de operação voltava a aparecer na Visão geral do
    # Inventário — caixa de uma feira que já acabou, na bancada de quem
    # trabalha no depósito.
    is_fair_register = fields.Boolean(
        string='Fair register', default=False, index=True, copy=False,
        help="Operation type of a fair's cash register. It never shows in "
             "the Inventory Overview: the warehouse does not work it.")

    fair_id = fields.Many2one(
        # NÃO é cascade: a transferência guarda o tipo de operação, e uma
        # operação apagada junto com a feira deixaria movimento apontando
        # para o vazio. A feira morre; o histórico dela fica de pé.
        'event.fair', string='Fair', ondelete='set null', index=True,
        help="Set on the operation type the fair's cash register uses. Any "
             "transfer of this type belongs to that fair.")
