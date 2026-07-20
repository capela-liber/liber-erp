# -*- coding: utf-8 -*-
{
    'name': 'Copyright Contracts - Author Reports',
    'version': '19.0.1.0.0',
    'summary': 'Royalty statements sent to authors (PDF report + email)',
    'description': """
Author-facing reporting layer for copyright contracts.

Adds an Authors menu (contacts that are beneficiaries of at least one royalty
line), an Author page on the contact form (personal/bank data used by the
statement, IRRF percentage, royalty lines across all contracts and the open
balance), and a "Prestação de contas" (royalty statement): a QWeb PDF report
that consolidates, per author, the royalties accrued in a period across all
their contracts and works, one row per work/channel, with the IRRF deduction
and the net amount to receive.

A wizard (button on the author form) picks the period and either prints the
statement or emails it to the author with the PDF attached; the send is logged
on the author's chatter and noted on each contract involved.
""",
    'author': 'EdLab Press',
    'category': 'Sales/Contracts',
    'depends': ['liber_copyright_contracts_payments'],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_template_data.xml',
        'report/royalty_statement_templates.xml',
        'report/royalty_statement_reports.xml',
        'wizard/statement_wizard_views.xml',
        'views/partner_views.xml',
        'views/authors_menu.xml',
    ],
    'demo': [
        'demo/books_demo.xml',
        'demo/books_invoices_demo.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
