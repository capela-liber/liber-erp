# -*- coding: utf-8 -*-
{
    'name': 'Cloud Files (base)',
    'version': '19.0.0.1.0',
    'summary': 'The chassis under Dropbox, Google Drive and GitHub: '
               'per-folder ACLs, sharing ledger, links and tags',
    'description': """
One chassis, several shelves.

The publisher's files live in cloud storages -- Dropbox, Google Drive,
GitHub -- each with a single company credential that cannot say who reads
and who writes. This base module is the gate they all share: folders mapped
per company, read/write decided group by group, downloads through the door,
uploads that never overwrite, shared links signed and dated, tags and links
to authors and titles.

It ships no menu and no provider. Each provider module contributes its
client (one file), its credentials fields, and its own app entry -- teams
that live in different tools get different doors to the same discipline.
""",
    'author': 'EdLab Press',
    'category': 'Productivity/Documents',
    'depends': ['base_setup', 'product'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/liber_cloud_security.xml',
        'security/ir.model.access.csv',
        'data/liber_cloud_cron.xml',
        'views/cloud_account_views.xml',
        'views/cloud_file_views.xml',
        'wizard/cloud_upload_views.xml',
        'views/cloud_folder_views.xml',
        'views/cloud_tag_views.xml',
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
