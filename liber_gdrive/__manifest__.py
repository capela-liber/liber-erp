# -*- coding: utf-8 -*-
{
    'name': 'Google Drive Files',
    'version': '19.0.0.1.0',
    'summary': 'The Google Drive shelf on the Cloud Files chassis',
    'description': """
Google Drive is the shelf, Odoo is the gate.

The Drive body on the liber_cloud_files chassis: the API client, the
credential fields on the cloud account, and its own app entry with its
own groups. Folder ACLs, the write gate, uploads, shared links with a
deadline, tags and links to authors and titles all come from the base --
identical across Dropbox, Google Drive and GitHub.

Drive peculiarities, honestly kept: folders are addressed by ID (fill in
the External ID from the folder's URL), downloads stream through Odoo
(Drive has no anonymous temporary links), and link expiration needs a
paid Workspace edition.
""",
    'author': 'EdLab Press',
    'category': 'Productivity/Documents',
    'depends': ['liber_cloud_files'],
    'data': [
        'security/liber_gdrive_security.xml',
        'views/cloud_account_views.xml',
        'views/liber_gdrive_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'AGPL-3',
}
