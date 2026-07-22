# -*- coding: utf-8 -*-
{
    'name': 'GitHub Files',
    'version': '19.0.0.1.0',
    'summary': 'The GitHub shelf on the Cloud Files chassis',
    'description': """
GitHub is the shelf, Odoo is the gate.

The GitHub body on the liber_cloud_files chassis: the API client, the
token field on the cloud account, and its own app entry with its own
groups. Folder ACLs, the write gate, uploads, tags and links to authors
and titles all come from the base -- identical across Dropbox, Google
Drive and GitHub.

GitHub peculiarities, honestly kept: a "folder" is a repository (plus an
optional subdirectory and branch), every upload is a commit signed by the
Liber, the revision is the blob's SHA, and the "shared link" only opens
for people who can see the repository -- for once, a share that does NOT
pierce the gate.
""",
    'author': 'EdLab Press',
    'category': 'Productivity/Documents',
    'depends': ['liber_cloud_files'],
    'data': [
        'security/liber_github_security.xml',
        'views/cloud_account_views.xml',
        'views/cloud_folder_views.xml',
        'views/liber_github_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'AGPL-3',
}
