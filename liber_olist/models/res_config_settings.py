# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    olist_despacho_politica = fields.Selection([
        ('com_nota', "Só com nota"),
        ('sem_nota', "Com ou sem nota"),
    ], string="Despachar pedidos do Olist", default='com_nota',
        config_parameter='liber_olist.despacho_politica',
        help="'Só com nota' (padrão): o pedido entra na fila de despacho "
             "quando o Olist já emitiu a nota dele — a caixa viaja com a "
             "DANFE. 'Com ou sem nota': o pedido entra na fila assim que "
             "chega; a fatura alcança o pedido sozinha quando a nota vier "
             "pelo sync, inclusive se a entrega já tiver sido validada.")
