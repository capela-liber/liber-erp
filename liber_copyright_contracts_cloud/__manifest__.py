# -*- coding: utf-8 -*-
{
    'name': 'Copyright Contracts - Cloud Documents',
    'version': '19.0.1.2.2',
    'summary': "Link each contract to its documents in Dropbox, Google "
               "Drive or GitHub",
    'description': """
Bridge between copyright contracts and the Cloud Files family.

A contract points at its documents -- the signed contract, amendments,
renewals -- in whichever storage the house keeps them (Dropbox, Google
Drive, GitHub), through the files Cloud Files already mirrors. Settings >
Copyright > Documents chooses the storage (GitHub, Google Drive or Dropbox)
and, in it, the mapped folders that hold contracts; the document picker of
a contract only offers files from those folders.

One document is the main one, and its file name fills the contract's
Location. Opening a document goes through the folder's read ACL, exactly
like opening it from Cloud Files.
""",
    'author': 'EdLab Press',
    'category': 'Sales/Contracts',
    'depends': ['liber_copyright_contracts', 'liber_cloud_files'],
    'data': [
        'security/ir.model.access.csv',
        'security/contract_cloud_security.xml',
        'views/res_config_settings_views.xml',
        'views/contract_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_copyright_contracts_cloud/static/src/js/contract_documents_tour.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
