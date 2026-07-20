# -*- coding: utf-8 -*-
{
    'name': 'Budget (Open)',
    'version': '19.0.1.0.0',
    'summary': 'Orcamentos abertos sobre a Contabilidade Analitica (sem Enterprise)',
    'category': 'Accounting/Accounting',
    'author': 'EdLab Press',
    'license': 'AGPL-3',
    'depends': ['analytic', 'account'],
    'data': [
        'security/budget_security.xml',
        'security/ir.model.access.csv',
        'views/budget_analytic_views.xml',
        'views/budget_position_views.xml',
        'views/budget_group_views.xml',
        'views/budget_tag_views.xml',
        'views/budget_report_views.xml',
    ],
    'demo': [
        'data/budget_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_budget/static/src/scss/budget.scss',
        ],
    },
    'installable': True,
    'application': True,
    'post_init_hook': 'post_init_hook',
}
