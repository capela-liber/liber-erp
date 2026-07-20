# -*- coding: utf-8 -*-
{
    'name': 'Copyright Contracts - Taxes (IRRF)',
    'version': '19.0.1.0.0',
    'summary': 'Withholding income tax (IRRF) on author royalty payments',
    'description': """
Withholding tax layer for copyright contracts (Brazilian IRRF).

Computes the IRRF withheld from each author payment bill following the
accountant's method (progressive table + Lei 15.270/2025 reducer, simplified
discount, no withholding up to the configured income limit). The withholding
is booked as a negative line on the author's bill (payable = net) against the
"IRRF to pay" liability account, and accumulated on a single draft vendor
bill addressed to the government contact: one line per work, batch number as
the Bill Reference ("Impostos de Direitos Autorais/NNN") and the source
contracts/bills listed in the Payment Reference. Bills are linked by
relational fields, so the link survives any draft/posted state combination.

The tax table is configurable data (Copyright > Configuration > IRRF Tables)
so the accountant can maintain it when the law changes.
""",
    'author': 'EdLab Press',
    'category': 'Sales/Contracts',
    'depends': ['liber_copyright_contracts_reports'],
    'data': [
        'views/res_config_settings_views.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/irrf_table_2026.xml',
        'views/irrf_table_views.xml',
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
    ],
    'demo': [
        'demo/taxes_demo.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
