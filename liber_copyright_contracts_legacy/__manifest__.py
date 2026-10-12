# -*- coding: utf-8 -*-
{
    'name': 'Copyright Contracts - Legacy Sales',
    'version': '19.0.1.5.0',
    'summary': 'Royalties on the sales made before Odoo, classified by '
               'CFOP and corrected by a price index',
    'description': """
Legacy sales layer for copyright contracts.

A publishing house that adopts Odoo rarely starts from zero: years of sales
live in the systems it used before, and royalty contracts reach back into
them -- the tier a contract pays depends on every copy sold, not only on the
ones Odoo invoiced. Exported as one row per invoice line, with the CFOP of
each line, that history comes in through this module:

* imports that base (CSV or XLSX) into **Copyright > Legacy Sales** with a
  bulk COPY, links each row to the product by ISBN (barcode / ISBN /
  internal reference) and keeps the quality flags of the unification;
* classifies every row by **CFOP**: a sale (5101, 6101, 5113, 6113...)
  accrues royalties, a return (1201, 2201...) deducts them, a consignment
  shipment (5917, 6917), a transfer or a sample is neutral, a donation is
  a courtesy and pays nothing. The table is data (Copyright >
  Configuration > Legacy CFOP) and a row can be overridden by hand;
* keeps **price indexes** (IPCA shipped, refreshed from the Central Bank of
  Brazil) so an old sale can be corrected to today's money;
* adds a **Legacy sales** option to the contract: switch it on, choose the
  index (or none, for nominal values) and the reference month, and the
  contract books one analytic entry per month of legacy sales on the same
  analytic account as the invoiced royalties. Legacy copies also count in
  the cumulative quantity that selects the royalty tier;
* shows the author, in the royalty statement, the **correction applied per
  year**: copies, the money of the time, the index factor, the corrected
  base and the royalty on it.
""",
    'author': 'EdLab',
    'category': 'Sales/Contracts',
    'depends': ['liber_copyright_contracts_reports', 'liber_knowledge'],
    'external_dependencies': {'python': ['openpyxl', 'requests']},
    'data': [
        'security/legacy_security.xml',
        'security/ir.model.access.csv',
        'data/legacy_cfop_data.xml',
        'data/price_index_ipca.xml',
        'views/price_index_views.xml',
        'views/legacy_cfop_views.xml',
        'wizard/legacy_import_wizard_views.xml',
        'wizard/legacy_link_product_views.xml',
        'views/legacy_sale_views.xml',
        'views/contract_views.xml',
        'views/account_analytic_line_views.xml',
        'views/menus.xml',
        'report/royalty_statement_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_copyright_contracts_legacy/static/src/js/legacy_sales_tour.js',
            'liber_copyright_contracts_legacy/static/src/js/contract_buttons_tour.js',
            'liber_copyright_contracts_legacy/static/src/js/legacy_channel_tour.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
