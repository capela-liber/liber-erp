# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    # O `liber_nfe_remessa` já reservava 'event' num comentário, esperando
    # este módulo: a feira é o terceiro tipo de remessa da casa, depois da
    # consignação e da bonificação.
    remessa_origin = fields.Selection(selection_add=[('event', 'Fair')])
    fair_id = fields.Many2one(
        'event.fair', string='Fair', index=True, ondelete='set null',
        copy=False)
