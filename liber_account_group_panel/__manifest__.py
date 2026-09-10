{
    'name': 'Chart of Accounts Group Panel',
    'summary': 'Filter the Chart of Accounts by account group instead of the first two code digits',
    'description': """
The search panel of the Chart of Accounts is bound to ``account.root``, a
model whose whole definition is "the first two characters of the account
code". With a dotted chart of accounts (``1.1.1``, ``3.2.4``) the second
character is the dot itself, so the panel degenerates into ``1``, ``1.``,
``2``, ``2.``, ``3``, ``3.`` and filters nothing useful.

This module points that search panel at ``account.group`` instead, so the
sidebar shows the real chart hierarchy - Assets / Current Assets / Cash and
Cash Equivalents - collapsible, with record counts.

No data is stored and no field is added. ``account.account.group_id`` stays
the non-stored compute the core defines; the module only teaches the ORM how
to express it in SQL, the same way the core already does for ``root_id``, so
grouping and filtering on it work without any recomputation.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': 'EdLab Press',
    'website': 'https://liber.edlab.press',
    'license': 'AGPL-3',
    'depends': ['account'],
    'data': ['views/account_account_views.xml'],
    'assets': {
        'web.assets_backend': [
            'liber_account_group_panel/static/src/js/account_group_panel_tour.js',
        ],
    },
    'installable': True,
}
