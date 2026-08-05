# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    """O caminho de volta: da cotação para o pedido da Amazon que a gerou.

    Sem isto, descobrir de onde veio uma cotação depende de ler o
    `client_order_ref` e procurar à mão. Com isto, é um campo.
    """
    _inherit = 'sale.order'

    amazon_order_ids = fields.One2many(
        'liber.amazon.order', 'sale_order_id', string='Amazon Purchase Orders',
        readonly=True)
