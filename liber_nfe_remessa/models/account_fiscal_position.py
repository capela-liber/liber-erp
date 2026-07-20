# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    # Same names as Odoo 15 production (module edoo_invoice_paid), on purpose:
    # the eleven fiscal positions configured there -- devoluções, feiras,
    # remessas, the BONI account -- migrate onto these fields one to one.
    #
    # O15 implemented it by swapping the payment-term line onto this account
    # (one document, no counter-entry). O19 forbids that swap by construction:
    # on a sale document, payment_term line XOR receivable account raises.
    # So here the invoice posts normally and is immediately settled against
    # this account and reconciled -- same outcome ("Paid", nothing owed),
    # with an auditable counter-entry instead of a mutated line.
    auto_invoice_paid = fields.Boolean(
        string="Auto Invoice Paid",
        help="Notes under this fiscal position never generate payment: on "
             "posting, the receivable is settled against the account below "
             "and reconciled automatically.")
    auto_invoice_paid_account_id = fields.Many2one(
        'account.account', string="Auto Invoice Paid Account",
        check_company=True,
        help="Counterpart account for the automatic settlement (e.g. a "
             "'Remessa de mercadoria' mirror account).")
