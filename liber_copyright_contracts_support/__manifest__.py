# -*- coding: utf-8 -*-
{
    'name': 'Copyright Contracts - Author Support',
    'version': '19.0.1.1.0',
    'summary': "Missions: write to the authors of a set of contracts and "
               "follow every reply as a support ticket",
    'description': """
Author support for copyright contracts, on top of Liber Support.

The royalties department talks to authors in missions: a royalty statement
to send, a settlement to agree, a registration to update. A mission is a
set of contracts, a message template and, when it applies, the statement
PDF of each author. Sending it opens ONE support ticket per author of the
selected contracts (an author on five contracts gets one e-mail listing the
five works) on the "Authors" team, and the e-mail goes out from the ticket,
so the author's reply lands in it -- not in a mailbox nobody reads.

The author's contact card is the author's folder: a tab lists every ticket
of that author, mission or not, in time order; the contract lists the
tickets that mention it. An author who writes on their own to the team's
alias becomes a ticket on the same card.
""",
    'author': 'EdLab Press',
    'category': 'Sales/Contracts',
    'depends': ['liber_copyright_contracts_reports', 'liber_support'],
    'data': [
        'security/ir.model.access.csv',
        'security/mission_security.xml',
        'data/support_team_data.xml',
        'data/mail_template_data.xml',
        'data/ir_cron.xml',
        'views/mission_views.xml',
        'views/support_ticket_views.xml',
        'views/partner_views.xml',
        'views/contract_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_copyright_contracts_support/static/src/js/author_mission_tour.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
