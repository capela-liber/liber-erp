# -*- coding: utf-8 -*-
{
    'name': 'Copyright Contracts - Analytics',
    'version': '19.0.1.0.0',
    'summary': 'Analytic accounts and payment tracking for copyright contracts',
    'description': """
Analytics layer for copyright contracts.

Adds an analytic account and a last-payment date to each royalty line
(work x beneficiary). The analytic account is named after the contract
number, the product internal reference, the product and the beneficiary.
The last payment date can only be edited by a Contracts Administrator.
""",
    'author': 'EdLab Press',
    'category': 'Sales/Contracts',
    'depends': ['liber_copyright_contracts', 'analytic', 'account', 'sales_team'],
    'data': [
        'data/analytic_plan.xml',
        'views/res_config_settings_views.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'wizard/analytic_wizard_views.xml',
        'views/contract_views.xml',
        'views/analytic_account_menu.xml',
        'views/res_company_views.xml',
        'views/account_move_views.xml',
        'views/account_analytic_line_views.xml',
        'views/report_menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
