# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    metabrasil_shipped_date = fields.Date(
        string='Printer Shipped On', copy=False, readonly=True,
        help="Day Metabrasil reported this print order as shipped.")
    metabrasil_delivered_date = fields.Date(
        string='Printer Delivered On', copy=False, readonly=True,
        help="Day Metabrasil reported this print order as delivered.")
    metabrasil_tracking_url = fields.Char(
        string='Printer Tracking URL', copy=False,
        help="Carrier tracking page reported by Metabrasil; also what the "
             "Tracking button opens for metabrasil deliveries.")
    metabrasil_status = fields.Selection(
        related='purchase_id.metabrasil_status', string='Print Status',
        store=True)
