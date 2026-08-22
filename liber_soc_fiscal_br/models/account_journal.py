# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    remessa_kind = fields.Selection(
        selection_add=[('consignment', "Consignação")],
        ondelete={'consignment': 'set default'})
