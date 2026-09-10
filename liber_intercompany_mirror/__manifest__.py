# -*- coding: utf-8 -*-
{
    'name': 'Intercompany Mirror Link',
    'version': '19.0.1.0.0',
    'summary': 'See and open the mirror document created in the sister company',
    'description': """
Intercompany Mirror Link
========================

``account_invoice_inter_company`` (OCA) creates, when an invoice or bill is
posted with a sister company as partner, the counterpart document in that
company. It keeps the link in a field, but shows nothing on screen: the person
who posted the invoice has no way to find the mirror except by searching the
other company's list by reference.

This module puts the link where it is needed:

* on the source document, a **Mirror** smart button with the count, opening
  the counterpart(s);
* on the mirror, a **Source** smart button and the *Source document* field in
  the *Other Info* tab.

Opening a document of the other company needs that company enabled in the
company switcher, as for any multi-company record.
""",
    'category': 'Accounting/Accounting',
    'author': 'Capela Liber',
    'website': 'https://liber.edlab.press',
    'license': 'AGPL-3',
    'depends': ['account_invoice_inter_company'],
    'data': [
        'views/account_move_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_intercompany_mirror/static/src/js/mirror_link_tour.js',
        ],
    },
    'installable': True,
    'application': False,
}
