# -*- coding: utf-8 -*-
{
    'name': 'Consignment - Settlement',
    'version': '19.0.2.3.0',
    'summary': 'Consignment settlement: turn what the customer sold into a real sale',
    'description': """
Consignment settlement (SOC redesign).

The settlement is the ONLY place where consignment becomes a sale. From the
customer's physical count it reconciles what was sold (expected on shelf minus
reported on hand), generates a normal sale.order for the sold quantity, and
takes the sold stock off the shelf (shelf -> customers) through a real stock
transfer. Nothing here pollutes the sales reports until the goods are actually
sold.
""",
    'author': 'EdLab Press',
    'category': 'Inventory/Consignment',
    'depends': ['liber_soc_agreements', 'liber_soc_moves', 'sale', 'liber_nfe_xml',
                'liber_metabooks_integration'],
    'data': [
        'security/soc_settlement_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/ir_sequence_campaign.xml',
        'data/settlement_stage_data.xml',
        'data/discuss_channel_data.xml',
        'data/ir_cron_finalize.xml',
        'data/mail_template_return.xml',
        'data/ir_cron_return_dunning.xml',
        'data/ir_cron_shelf_age.xml',
        'data/ir_cron_overdue.xml',
        'report/consignment_map_report.xml',
        'report/consignment_return_report.xml',
        'views/res_config_settings_views.xml',
        'views/consignment_settlement_views.xml',
        'views/consignment_ledger_views.xml',
        'views/shortfall_views.xml',
        'views/shelf_inventory_views.xml',
        'views/consignment_coverage_views.xml',
        'views/coverage_views.xml',
        'views/consigned_stock_age_views.xml',
        'views/consignment_template_campaign_views.xml',
        'views/consignment_move_views.xml',
        'views/consignment_agreement_views.xml',
        'views/related_documents_views.xml',
        'wizards/run_overstock_wizard_views.xml',
        'wizards/generate_wizard_views.xml',
        'wizards/map_run_wizard_views.xml',
        'views/soc_settlement_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_soc_settlement/static/src/scss/consignment_settlement_list.scss',
            'liber_soc_settlement/static/src/js/many2one_multi_field.js',
            'liber_soc_settlement/static/src/js/soc_acerto_tour.js',
        ],
    },
    'post_init_hook': 'post_init_backfill_campaign_codes',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
