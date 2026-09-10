# -*- coding: utf-8 -*-
"""Quantos exemplares há NA MESA, no cartão do produto.

Quem vende numa feira precisa saber o que ainda tem em cima da mesa — não o
que existe no armazém, a seiscentos quilômetros. O balcão do PDV não mostra
estoque por padrão, e o que ele mostra no botão de informação é o do armazém.

Aqui a quantidade é a da LOCALIZAÇÃO DA FEIRA, e ela viaja para o balcão junto
com os produtos, num campo só. Sem isso, saber se ainda há um exemplar
significa olhar a pilha — que é exatamente o que ninguém consegue fazer com
fila na frente.
"""
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    fair_qty = fields.Float(
        string='On the table', digits='Product Unit',
        compute='_compute_fair_qty',
        help="Copies of this title on the table of the fair whose register "
             "is open. Zero everywhere else.")

    @api.depends_context('fair_location_id')
    def _compute_fair_qty(self):
        local = self.env.context.get('fair_location_id')
        if not local:
            for produto in self:
                produto.fair_qty = 0.0
            return
        for produto in self.with_context(location=local):
            produto.fair_qty = produto.qty_available

    @api.model
    def _load_pos_data_fields(self, config):
        campos = super()._load_pos_data_fields(config)
        if 'fair_qty' not in campos:
            campos = campos + ['fair_qty']
        return campos
