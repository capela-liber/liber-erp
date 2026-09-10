# -*- coding: utf-8 -*-
{
    'name': 'Aged Payable',
    'version': '19.0.1.10.0',
    'summary': 'Open vendor balances by partner and age bracket, with a jump '
               'to the document and to manual reconciliation',
    'description': """
The twin of ``liber_aged_receivable``, looking at the other side of the
ledger: what the house owes, by vendor and by age.

Same shape and same reasons - Aged Payable is Enterprise
(``account_reports``), the Community 19 ships nothing in its place, and the
OCA module prints a PDF instead of letting anyone walk from the overdue line
to the bill and settle it.

Two differences from the receivable side, both deliberate:

* **The sign is flipped.** A payable lives on the credit side of the ledger,
  so the raw residual is negative. The screen shows the debt positive, which
  is the convention the Enterprise report follows and the one an accountant
  reads without translating in their head. The ledger is untouched: the
  inversion happens in the SELECT.
* **The partner is the vendor**, and the buckets read as "how long has this
  bill been sitting unpaid" rather than "how long has this customer owed us".

It depends on ``liber_aged_receivable`` because the engine
(``liber.aged.balance.abstract``) lives there: the bracket arithmetic, the
ORM-cache flush and the two jump buttons are one implementation, so a fix
reaches both screens instead of one.
""",
    'category': 'Accounting/Accounting',
    'author': 'EdLab Press',
    'website': 'https://liber.edlab.press',
    'license': 'AGPL-3',
    'depends': ['liber_aged_receivable'],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'views/liber_aged_payable_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_aged_payable/static/src/js/aged_payable_tour.js',
        ],
    },
    'installable': True,
}
