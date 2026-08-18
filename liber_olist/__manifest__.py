# -*- coding: utf-8 -*-
{
    'name': "Olist Integration",
    'summary': "Pull NFe XMLs from Olist/Tiny into nfe_xml",
    'description': """Olist as an ADAPTER, not as the system of record.

Odoo is the canonical ledger; Olist is one of several sources that can feed it
a fiscal document (an XML), exactly like a manual upload does. Removing this
module removes the integration and leaves the ledger intact - which is the whole
point: the previous fiscal stack became a black box we could not walk away from.

One account record per Olist account (the group runs several companies), each
bound to an Odoo company. A note is only imported if its XML names that
company's CNPJ.
""",
    'author': "EdLab",
    'category': 'Accounting',
    'version': '19.0.12.9.0',
    'license': 'LGPL-3',
    # `liber_metabooks_integration` porque a casa decidiu (17/08/2026) o que é o
    # CATÁLOGO: livro Metabooks do tipo pbook. Sem ele, "o que é nosso e ainda
    # não está no Olist" trazia 3.632 registros no staging -- serviços
    # editoriais, retirada de lucros e o catálogo de distribuição inteiro.
    'depends': ['liber_nfe_xml', 'liber_metabooks_integration'],
    'data': [
        'security/ir.model.access.csv',
        'security/olist_security.xml',
        'views/olist_menus.xml',
        'views/olist_account_views.xml',
        'views/olist_channel_views.xml',
        'views/olist_product_views.xml',
        'views/olist_catalog_views.xml',
        'views/olist_absent_views.xml',
        'views/olist_order_views.xml',
        'views/product_views.xml',
        'data/olist_cron.xml',
    ],
    'application': False,
}
