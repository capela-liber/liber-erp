# -*- coding: utf-8 -*-
{
    'name': 'Dropbox Files',
    'version': '19.0.0.1.0',
    'summary': 'Per-folder read/write access and simple sharing over the company Dropbox',
    'description': """
Dropbox is the shelf, Odoo is the gate.

The files stay in Dropbox, under the one company account. This module maps
chosen Dropbox folders into Odoo and lets Odoo decide who reads and who
writes: per-folder groups, enforced by record rules and checked again in
every method that touches the API. Users never receive Dropbox credentials.

Sharing is deliberate. A button creates the Dropbox shared link and records
who asked for it -- and anyone holding that link bypasses Odoo, because that
is what a Dropbox shared link is. Creating one is a right, not a default.
""",
    'author': 'EdLab Press',
    'category': 'Productivity/Documents',
    'depends': ['base_setup', 'product'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/liber_dropbox_security.xml',
        'security/ir.model.access.csv',
        'views/dropbox_file_views.xml',
        'wizard/dropbox_upload_views.xml',
        'views/dropbox_folder_views.xml',
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/liber_dropbox_menus.xml',
        'views/dropbox_tag_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'AGPL-3',
}
