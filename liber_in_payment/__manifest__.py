{
    'name': 'Invoice "In Payment" State',
    'summary': 'Show the In Payment state on invoices in Odoo Community',
    'description': """
Odoo Community hides the "In Payment" state: as soon as an invoice is
reconciled with a payment it shows "Paid", even when the money is still
sitting on an outstanding account waiting for the bank statement.

This module restores the Enterprise behaviour: an invoice reconciled with a
payment whose outstanding line is not yet matched with a bank statement shows
"In Payment"; it only becomes "Paid" once the statement confirms the money.

Requires outstanding accounts to be set on the journals' payment method
lines — without them, payments are considered matched immediately and the
invoice still goes straight to "Paid".
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': 'EdLab Press',
    'website': 'https://liber.edlab.press',
    'license': 'AGPL-3',
    'depends': ['account'],
    'data': ['views/res_config_settings_views.xml'],
    'installable': True,
}
