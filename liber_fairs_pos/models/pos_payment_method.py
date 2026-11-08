# -*- coding: utf-8 -*-
from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    # A GAVETA reaproveitável dos caixas de feira. Ver `res_company.py`.
    fair_drawer = fields.Boolean(
        string='Fair cash drawer', readonly=True, copy=False,
        help="Cash drawer lent to one fair register at a time. It comes "
             "back when the fair returns, and the next register takes it.")
