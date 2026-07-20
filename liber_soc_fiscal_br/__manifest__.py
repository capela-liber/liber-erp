# -*- coding: utf-8 -*-
{
    'name': 'Consignment - Fiscal (BR)',
    'version': '19.0.2.2.0',
    'summary': 'Consignment stock valuation: consigned goods held in their own asset account',
    'description': """
Consignment fiscal/accounting layer (SOC redesign).

Option (c): a consignment shelf keeps our goods (usage='internal', still ours,
still counted in On Hand and on_shelf_qty), but its *value* is re-qualified into
a dedicated asset account (e.g. 115000 "Consignment Stock at customers") instead
of the normal Inventory account.

Mechanism -- a single, surgical override:

    stock.location._should_be_valued() -> False for consignment shelves.

With that, stock_account treats a warehouse -> shelf move as a valued *out* and a
shelf -> warehouse move as a valued *in*, posting:

    shipment  WH -> shelf : Dr 115000 (Consignment) / Cr Inventory
    return    shelf -> WH : Dr Inventory            / Cr 115000

No sale.order, no invoice, no receivable -- a consignment movement is NOT a sale.
The balance of 115000 equals the value currently consigned; Inventory holds only
the non-consigned stock. Physical quantities are untouched (the shelf stays
internal), so every quantity-based feature keeps working.

PREREQUISITE (company-wide accounting decision, NOT done by this module):
the products' category valuation must be 'real_time' (perpetual). The entries
above only fire for real_time products. Set the Consignment Stock Account in
Inventory Settings and run "Wire consignment shelves" to backfill existing ones.
""",
    'author': 'EdLab Press',
    'category': 'Inventory/Consignment',
    'depends': ['liber_soc_agreements', 'liber_soc_moves', 'liber_soc_settlement', 'stock_account', 'account', 'liber_nfe_xml', 'liber_nfe_remessa'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
