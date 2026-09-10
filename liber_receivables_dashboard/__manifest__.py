# -*- coding: utf-8 -*-
{
    'name': 'Liber Receivables History',
    'version': '19.0.2.0.0',
    'summary': 'A monthly snapshot of the receivables portfolio by age bracket, '
               'and the days-to-due column the Assets dashboard reads',
    'description': """
The aging report (``liber_aged_receivable``) only knows how the portfolio
stands today: it cannot say how much was overdue in March. This module
photographs the portfolio once a month, by company and by age bracket, so
the history exists -- **Receivables History**, under Accounting > Reporting,
with a list and a graph. The cron runs on the 1st; one snapshot per month and
company, replaceable at any time with "Take today's snapshot"; the first one
is taken on install.

The portfolio is the posted, positive, real-customer part of the aging
report; customer credits and lines whose partner never was a customer are
kept in buckets of their own, outside the portfolio.

History: the module was born on 06/09/2026 with a "Receivables" dashboard
that opened the Assets figure into brackets, calendar, concentration and
channels. On the same day the owner moved those pieces into the Assets
dashboard itself (``edlab_stack``) and retired the separate dashboard; the
snapshot stayed here. The module keeps its technical name.
""",
    'category': 'Accounting/Accounting',
    'author': 'EdLab Press',
    'website': 'https://liber.edlab.press',
    'license': 'AGPL-3',
    'depends': [
        'liber_aged_receivable',
        'spreadsheet_dashboard_account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'views/receivables_snapshot_views.xml',
        'data/ir_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_receivables_dashboard/static/src/js/receivables_history_tour.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
