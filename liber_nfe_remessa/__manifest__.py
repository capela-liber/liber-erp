# -*- coding: utf-8 -*-
{
    'name': "Nota de Remessa",
    'summary': "Fiscal documents that never generate payment (simples remessa)",
    'description': """
The REM/ document: an invoice-shaped fiscal note that never generates payment.

Consignment shipments, bonus copies, event material -- in Brazil every one of
them needs a nota fiscal, and none of them is a sale. Odoo 15 production solved
this with edoo_invoice_paid: two fields on the fiscal position swap the
receivable away. Odoo 19 forbids that exact swap by construction
(account_move_line.py: payment_term line XOR receivable account), so this
module does the closest legal thing: post the invoice normally, then
immediately settle the receivable against the account configured on the fiscal
position, and reconcile. Same configuration surface as production (field names
included, so the eleven O15 fiscal positions migrate 1:1); the only internal
difference is an auditable counter-entry instead of a mutated line.

The remessa journal (code REM) gives these documents their own sequence and
their own menu in Accounting, keeping Invoices strictly for real sales --
payment, bank and all.
    """,
    'author': "EdLab Press",
    'category': 'Accounting',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'views/account_fiscal_position_views.xml',
        'views/account_move_views.xml',
        'views/nfe_remessa_menus.xml',
    ],
    'installable': True,
    'application': False,
}
