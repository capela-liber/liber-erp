# -*- coding: utf-8 -*-
{
    'name': 'Copyright Contracts - Payments',
    'version': '19.0.1.0.0',
    'summary': 'Generate vendor bills to pay authors from open royalties',
    'description': """
Payments layer for copyright contracts.

Turns the open royalties tracked on each beneficiary's analytic account into
vendor bills to pay the authors. A company setting defines the product, the
expense account, the purchase journal and the number of days used for the due
date. Bills are created by an action (one bill per author, one line per work),
each line carrying the work's product and its analytic account. When a bill is
paid, the royalty line's last payment date is updated automatically, which lets
the analytics layer settle the corresponding period.
""",
    'author': 'EdLab Press',
    'category': 'Sales/Contracts',
    'depends': ['liber_copyright_contracts_analytics', 'account'],
    'data': [
        'data/payment_product.xml',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/contract_views.xml',
        'views/account_move_views.xml',
        'views/bills_menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
