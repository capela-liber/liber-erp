# -*- coding: utf-8 -*-

{
    'name': "NFe XML",
    'summary': 'NFe XML panel - imports NFe XML, standalone (no l10n_br stack).',
    'description': """
NFe XML panel: imports NFe XML documents and links them to invoices.
It does NOT emit documents to SEFAZ - import only.

Migrated to Odoo 19 and made standalone. Dropped the production-only
dependencies and everything tied to them:

- l10n_br_eletronic_document (a minimal local nfe.cfop model stands in
  for the localization's CFOP table)
- edoo_br_mde (edoo.mde inherit, MDE cron, company view anchor)
- edoo_br_edocs_send_schemas (edoc_id/edocs_status fields)
- crm (lead_id, nfe_pipeline)

Odoo 19 migration notes:

- The XML <-> invoice link is now carried by the NFe access key (chave de
  acesso): account.move.nfe_key stores the 44-digit key and the
  nfe_xml_panel_id Many2one is resolved through it, never through raw
  database ids, so the link survives exports/imports and can always be
  rebuilt from the documents themselves.
- The SSOC/RSO/SO/PO order flows and the vendor-bill comparison cron were
  dropped: they depended on models (soc.type, nfe.xml.wizard) that never
  existed here and were dead code since v15.

The DANFE rendering in report/ builds on pytrustnfe (Danimar Ribeiro,
Trustcode) and keeps its original attribution.
""",
    'author': "EdLab Press",
    'website': "https://capela.press",
    'category': 'Accounting',
    'version': '19.0.2.5.0',
    'license': 'AGPL-3',
    'depends': ['base', 'sale', 'stock', 'product', 'account', 'purchase'],

    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/nfe_xml_process_cron.xml',
        'data/nfe_sefaz_cron.xml',
        'data/nfe_cfop_data.xml',
        'views/soc_xml_panel.xml',
        'views/nfe_xml_cancel_event.xml',
        'views/account_move_views.xml',
        'views/soc_xml_tags_view.xml',
        'views/soc_xml_items_view.xml',
        'views/soc_ir_attachment.xml',
        'views/res_partner_view.xml',
        'report/nfe_panel_report.xml',
        'data/xml_channel.xml',
        'views/nfe_xml_attachments.xml',
        'views/nfe_xml_painel.xml',
        'views/nfe_sefaz_views.xml',
        'wizard/import_xml_file.xml',
    ],
    'application': True,
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': False,
}
