# -*- coding: utf-8 -*-
"""A lista de preços que pertence a uma feira.

Sem o vínculo, cada abertura de caixa criaria outra lista com o mesmo nome, e
a casa acabaria com uma pilha de "Feira X (-50%)" idênticas.
"""
from odoo import fields, models


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    fair_id = fields.Many2one(
        'event.fair', string='Fair', ondelete='set null', index=True,
        copy=False,
        help="The event whose discount this pricelist carries.")
