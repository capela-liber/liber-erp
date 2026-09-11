# -*- coding: utf-8 -*-
{
    'name': 'Aged Receivable',
    'version': '19.0.1.11.0',
    'summary': 'Open customer balances by partner and age bracket, with a jump '
               'to the document and to manual reconciliation',
    'description': """
The Aged Receivable report is Enterprise (``account_reports``), and the
Community 19 has nothing in its place - the string exists in the translation
files of ``account`` and nowhere else. The OCA does ship an Aged Partner
Balance in ``account_financial_report``, but it is a wizard that PRINTS: you
choose the brackets, you get a PDF. That answers "how much is overdue" and
not "which payment do I go settle now".

This module answers the second question. It is a read-only SQL view over the
open lines of the receivable accounts, so it never goes stale and never needs
a cron: the brackets are computed against ``CURRENT_DATE`` at query time.

Because it is a plain Odoo model, everything the framework gives comes for
free - group by partner and the brackets add up per group, exactly like the
Enterprise screen; filter, search, sort, export to spreadsheet; and, on each
line, two buttons:

* **Open** jumps to the invoice or the payment itself;
* **Reconcile** jumps to the OCA reconciliation screen already positioned on
  that partner and that account, which is where the manual settlement is done.

Brackets follow the Enterprise convention - Not due, 1-30, 31-60, 61-90,
91-120, Older - measured from the DUE DATE (``date_maturity``), falling back
to the entry date when a line carries no due date.

Lines with no partner are kept, not hidden. In the migrated books they are
1.270 lines that no aging report would ever show, and hiding them would make
the total disagree with the ledger.
""",
    'category': 'Accounting/Accounting',
    'author': 'EdLab Press',
    'website': 'https://liber.edlab.press',
    'license': 'AGPL-3',
    'depends': ['account', 'account_reconcile_oca', 'liber_partner_group',
                'sale'],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'views/liber_aged_receivable_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_aged_receivable/static/src/js/aged_receivable_tour.js',
        ],
    },
    'installable': True,
}
