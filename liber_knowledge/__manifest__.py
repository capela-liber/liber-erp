{
    'name': 'Liber Knowledge',
    'summary': 'Internal wiki with the Liber manuals, on top of the OCA document_page',
    'description': """
Internal knowledge base: manuals, procedures and FAQ, inside Odoo and only
for internal users.

The wiki itself is the OCA ``document_page`` (pages, categories, version
history with diff) plus ``document_page_access_group`` (restrict a page to
groups or users). This module adds the house rules:

* the app is called "Manual", has its own icon, sits next to Training on
  the home screen and opens on the Manuals reader;
* every internal user reads the wiki; portal and public users never do;
* settings administrators manage it;
* the Liber manuals published in ``liber_site/static/docs`` are copied into
  the "Manuais do Liber" category, one page per manual, in the same areas
  as the site. The copy runs on install, on every update and from
  Knowledge > Configuration > Update Liber manuals. A page edited here is
  never overwritten.
""",
    'version': '19.0.1.3.0',
    'category': 'Knowledge',
    'author': 'EdLab Press',
    'website': 'https://liber.edlab.press',
    'license': 'AGPL-3',
    'depends': ['document_page', 'document_page_access_group'],
    'data': [
        'security/liber_knowledge_security.xml',
        'data/document_page_data.xml',
        'views/document_page_views.xml',
        'views/reader_views.xml',
        'data/liber_manuals_sync.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_knowledge/static/src/reader/reader.js',
            'liber_knowledge/static/src/reader/reader.xml',
            'liber_knowledge/static/src/reader/reader.scss',
            'liber_knowledge/static/src/js/knowledge_tour.js',
        ],
    },
    'installable': True,
}
