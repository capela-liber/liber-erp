# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMove(models.Model):
    """"Separar de" na própria linha da transferência interna.

    O formulário do core esconde De/Para das linhas (column_invisible) e só
    mostra a prateleira reservada atrás do botão Detalhes. Sem isto, a
    armadilha da raiz (ver stock_move_line.py) só aparece depois de validar.
    O campo lista as prateleiras de onde a reserva vai separar, para o 91->91
    ser visto antes do clique.
    """
    _inherit = 'stock.move'

    shelf_from = fields.Char(
        string='Pick From', compute='_compute_shelf_from',
        help="The locations the reservation picks from. On an internal "
             "transfer, if this is the destination shelf, nothing will move: "
             "set the source shelf in the Source Location.")

    @api.depends('move_line_ids.location_id', 'move_line_ids.quantity')
    def _compute_shelf_from(self):
        for move in self:
            locais = move.move_line_ids.filtered('quantity').location_id
            move.shelf_from = ', '.join(locais.mapped('name')) if locais else False
