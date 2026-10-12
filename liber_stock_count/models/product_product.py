# -*- coding: utf-8 -*-
from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _inverse_qty_available(self):
        # Escrever "Quantidade em mãos" na ficha é um ajuste de inventário
        # por outra porta. O core cria o quant como superusuário e aplica, e
        # a trava do quant veria o superusuário, não quem escreveu. A
        # pergunta é feita aqui, antes, com o usuário de fato.
        if not self.env.context.get('skip_qty_available_update'):
            self.env['stock.quant']._liber_check_can_apply_inventory()
        return super()._inverse_qty_available()
