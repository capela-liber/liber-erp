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

    # One journal per kind of remessa, mirroring `remessa_origin` on the move.
    # The reason is accounting, not tidiness: the account a remessa books to
    # differs by operation (consignment goes to the consignment investment
    # account, a bonus to its own), and in Odoo the account of last resort is
    # the journal's. One shared journal could only carry one of them.
    remessa_kind = fields.Selection(
        [('other', "Other")], string="Remessa kind",
        default='other', index=True,
        help="Which operation this remessa journal serves. Each kind books to "
             "its own account, carried by the journal.")
