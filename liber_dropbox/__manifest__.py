# -*- coding: utf-8 -*-
{
    'name': 'Dropbox Files',
    'version': '19.0.0.2.0',
    'summary': 'The Dropbox shelf on the Cloud Files chassis',
    'description': """
Dropbox is the shelf, Odoo is the gate.

The files stay in Dropbox, under each company's account. This module is
the Dropbox body on the liber_cloud_files chassis: it contributes the API
client, the credential fields on the cloud account, and its own app entry
with its own groups. Folder ACLs, the write gate, uploads, shared links
with a deadline, tags and links to authors and titles all come from the
base -- identical across Dropbox, Google Drive and GitHub.
""",
    'author': 'EdLab Press',
    'category': 'Productivity/Documents',
    'depends': ['liber_cloud_files'],
    'data': [
        'security/liber_dropbox_security.xml',
        'views/cloud_account_views.xml',
        'views/liber_dropbox_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'AGPL-3',
}
