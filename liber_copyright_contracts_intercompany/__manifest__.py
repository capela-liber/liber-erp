# -*- coding: utf-8 -*-
{
    'name': 'Copyright Contracts - Intercompany Royalties',
    'version': '19.0.1.3.0',
    'summary': 'Charge sister companies for royalties accrued on their sales',
    'description': """
Intercompany layer for copyright contracts.

One company of the group holds the copyright contracts (e.g. the publishing
house) while sister companies sell the works. This module:

* Formalizes WHICH companies' paid sales feed the royalty accrual of the
  contract-holding company (Settings > Copyright > Intercompany Royalties;
  empty = only the company's own sales).
* Stamps every royalty analytic entry with the company that made the sale,
  so own sales and sister-company sales stay distinguishable.
* Charges the selling company back: royalties accrued on a sister company's
  sales accumulate on a DRAFT customer invoice of the contract company
  addressed to the selling company (one line per contract x work x
  beneficiary, "Royalties entre Empresas" service product,
  optional markup), following the same accumulator pattern as the IRRF tax
  bill. Posting that invoice creates the mirrored draft vendor bill on the
  selling company, linked to it.

Deployment note: on the contract-holding company, set "Royalty source
companies" to the selling companies — with the module installed and the
setting empty, only the company's own sales accrue (which corrects the old
behaviour of silently sweeping every company's invoices).
""",
    'author': 'EdLab Press',
    'category': 'Sales/Contracts',
    'depends': ['liber_copyright_contracts_analytics'],
    'data': [
        'data/interco_product.xml',
        'data/ir_sequence.xml',
        'views/res_config_settings_views.xml',
        'views/account_move_views.xml',
        'views/account_analytic_line_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
