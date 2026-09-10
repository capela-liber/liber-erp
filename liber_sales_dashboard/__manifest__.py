# -*- coding: utf-8 -*-
{
    'name': 'Liber Sales Dashboard',
    'version': '19.0.1.1.0',
    'summary': 'The Sales dashboard reads two clocks: the order and the fiscal note',
    'description': """
A publishing house sells twice: once when the order is taken (the commercial
date, the channel, what is still to invoice) and once when the fiscal note
leaves (the NF-e date, what actually shipped with a document). The two never
match to the cent, and they should not -- the job of the dashboard is to show
both, one under the other, and to say how far apart they are.

This module rewrites the content of the core Sales dashboard (the same entry,
no second "Sales" in the sidebar):

* five cards, each compared with the previous period: Invoices (sales notes,
  net of items, without shipping), Orders, Closed orders (invoiced), Open
  orders (sold minus invoiced) and Invoices without order (notes whose
  invoice is not tied to any order);
* the revenue line, month by month, by note date;
* sold by orders and sold by notes, stacked by sales channel;
* the month-by-month tables, and the core's top quotations, top orders, top
  customers and top teams;
* a click on any card or chart opens the list it was computed from, with the
  dashboard period carried along.

It also gives the sales manager two lists under Sales > Fiscal notes (with
three filters that split a note by what it has behind it: without invoice,
invoice without order, tied to an order), and a
tz-aware ``order_date`` on the sales analysis (the core ``date`` is a UTC
datetime, and the month grouping slid one day back).

Needs ``liber_nfe_xml`` for the fiscal notes panel (``net_value``,
``book_qty``) and ``spreadsheet_dashboard_sale`` for the dashboard it
rewrites. If the core module is ever updated on its own, run ``-u`` on this
one to put the content back.
""",
    'author': 'Editora Hedra',
    'website': 'https://liber.edlab.press',
    'category': 'Sales/Sales',
    'license': 'AGPL-3',
    'depends': [
        'sale_management',
        'spreadsheet_dashboard_sale',
        'liber_nfe_xml',
    ],
    'data': [
        'views/nfe_xml_menus.xml',
        'views/nfe_xml_search.xml',
        'data/dashboard.xml',
    ],
    'assets': {
        # The same bundle where the core loads o-spreadsheet: the card patch
        # imports `@odoo/o-spreadsheet` and `@spreadsheet/actions/helpers`.
        'spreadsheet.o_spreadsheet': [
            'liber_sales_dashboard/static/src/js/cartao_leva_o_periodo.js',
        ],
        'web.assets_backend': [
            'liber_sales_dashboard/static/src/js/sales_dashboard_tour.js',
        ],
    },
    'installable': True,
    'application': False,
}
