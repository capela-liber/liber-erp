# -*- coding: utf-8 -*-
{
    'name': "Metabooks Books",

    'summary': """It is used to get book data from metabooks""",

    'description': """
Puxa metadados de livros da API Metabooks/MVB para o product.template
(título, editora/selo, autores, sinopse, preço, dados técnicos, capa). Importa
por ISBN avulso ou o catálogo inteiro de uma editora (VL / mvbId).

A documentação de testes (teste automático mockado + smoke test manual do sync
real, ex. editora BR0089701) está na página do módulo — Apps → Metabooks →
Module Info.
    """,

    'author': 'EdLab Press',
    'website': "https://capela.press",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '19.0.0.1',
    # Original v15 deps (kept for reference):
    # 'depends': ['base','stock','isbn_integration','br_account','account_accountant',
    #             'ean_creator','hedra_vendor_price_list_discount','website_sale', 'product'],
    # v19 port: l10n_br dropped — the only fiscal tie (NCM / fiscal_classification_id
    # via account.ncm) is disabled in v19, so this module no longer needs the Brazilian
    # localization. Book-metadata scope is independent of the fiscal stack.
    # hedra_vendor_price_list_discount dropped (custom v15 module, not used here); purchase
    # added for supplierinfo/pricelist fields the vendor views rely on.
    'depends': ['base', 'stock', 'purchase', 'website_sale', 'product'],
    'data': [
        'data/contributor_roles.xml',
        'data/metabooks_export_data.xml',
        'security/metabooks_security.xml',
        'security/ir.model.access.csv',
        'views/metabooks_menus.xml',
        'views/hedra_res_config.xml',
        'views/metabooks_product.xml',
        'views/metabooks_vendor.xml',
        'views/metabooks_models.xml',
        'views/metabooks_website.xml',
        'views/metabooks_export_metadata.xml',
        'views/metabooks_export_views.xml',
        'views/import_metadata_wizard.xml',
        'views/metabooks_import_job_views.xml',
        'wizards/metabooks_import_isbn_views.xml',
        'wizards/metabooks_import_vendor_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'liber_metabooks_integration/static/src/css/product_pdf.css',
        ],
    }
}