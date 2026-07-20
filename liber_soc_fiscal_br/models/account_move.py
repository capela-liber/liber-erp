# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    remessa_origin = fields.Selection(
        selection_add=[('consignment', "Consignação")],
        ondelete={'consignment': 'set default'})
