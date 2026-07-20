# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # What makes a journal a remessa journal is not its code but this flag:
    # documents in it are fiscal notes that never generate payment. The
    # Invoices menu excludes these journals; the Remessas menu shows them.
    is_remessa = fields.Boolean(
        string="Remessa journal",
        help="Documents in this journal are fiscal notes that never generate "
             "payment (simples remessa). They are excluded from Invoices and "
             "listed under Remessas instead.")
