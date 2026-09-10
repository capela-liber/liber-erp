# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # Um diário por tipo de remessa, e não um REM compartilhado: a conta de
    # último recurso mora no diário, e cada operação lança na sua. A feira é
    # o REM-F, ao lado do REM-C da consignação e do REM-B da bonificação.
    remessa_kind = fields.Selection(selection_add=[('event', 'Fair')],
                                    ondelete={'event': 'set default'})
