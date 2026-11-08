# -*- coding: utf-8 -*-
{
    'name': 'Copyright Contracts - Licensing',
    'version': '19.0.1.0.1',
    'summary': 'Reproduction-rights licensing: customer invoice from the '
               'contract, author share booked as a royalty',
    'description': """
Licensing layer for copyright contracts.

Sometimes the house sells the right to reproduce a work it holds (a poem in a
school anthology, an excerpt in an exam). The licence is billed to the
licensee with a customer invoice, and part of it belongs to the author.

* **Settings > Copyright > Licensing**: the product, income account and sales
  journal of licensing invoices, per company (the product falls back to the
  "Rights licensing" service shipped here);
* **Licensing % on each royalty line** (beneficiary x work), apart from the
  per-copy tiers: the author's share of every licence of that work;
* **"Licensing" smart button on the contract**: the contract's licensing
  invoices. Its standard *New* opens a customer invoice in the contract's
  company, already carrying the product, the account and, on the line, the
  beneficiary's analytic account;
* when that invoice is **paid**, the author's share (line amount x licensing
  %) is booked on the beneficiary's analytic account as an accrual -- so it
  recoups the advance, goes into the author's bill, pays IRRF and appears in
  the royalty statement, in its own **Licensing** section. Core's analytic
  entry for the full invoiced amount is NOT written on the author's account:
  that account holds what is owed to the author, not the house's revenue.
""",
    'author': 'EdLab Press',
    'category': 'Sales/Contracts',
    'depends': ['liber_copyright_contracts_reports'],
    'data': [
        'security/licensing_rules.xml',
        'data/license_product.xml',
        'views/contract_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'report/royalty_statement_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_copyright_contracts_licensing/static/src/js/licensing_tour.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
