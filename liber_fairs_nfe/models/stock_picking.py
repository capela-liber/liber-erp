# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Uma carga, uma nota. O carimbo é o que impede a segunda emissão de
    # declarar de novo o que já viajou: sem ele, apertar o botão duas vezes
    # numa feira com reposição emitiria a remessa inteira outra vez.
    fair_note_move_id = fields.Many2one(
        'account.move', string='Fair Remessa Note', readonly=True, copy=False)
