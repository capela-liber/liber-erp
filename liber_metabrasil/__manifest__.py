# -*- coding: utf-8 -*-
{
    'name': "Metabrasil Print-on-Demand",
    'summary': "Send print orders to Metabrasil, follow them home",
    'description': """
Print-on-demand connector for the Metabrasil bookprinter.

A clean-slate rewrite of the O15 metabrasil_odoo_connector (ksolves): same
API contract (/pedidos, /fretes), a fraction of the code, none of the dead
weight. What survives: the purchase order is POSTed to Metabrasil when
approved; a cron mirrors their status ladder (Included, Printing, Shipped,
Delivered) into a statusbar, carrying tracking codes back to the picking; a
delivery.carrier of type 'metabrasil' quotes freight through
/fretes/{cep}/rates/isbn; and overdue print orders raise activities instead
of silently rotting.

What changed on purpose: freight has ONE conversation, Odoo's own "Add
shipping". Pick the Dropship method, press "Get rate", and every transporter
Metabrasil quoted for that CEP is listed with its price and lead time --
cheapest preselected, another one a click away. There is no parallel print
quote window and no "deliver to our warehouse" question: the dropship route
already says where the books go, and the print order mirrors it (DROP_SHIP
when it carries a delivery address, EDITORA when the run lands at our depot).
Sale and print order link both ways -- a Print Orders button on the sale, the
originating sale on the print order.

There is no l10n_br dependency (CNPJ comes from partner.vat, the street
number is parsed out of the street line), no fiscal PATCH (DANFE upload
belongs to the future emission adapter, liber_olist, and
_metabrasil_fiscal_patch() is the hook it will fill) and no website flow
(freight quoting is backend-only).

The /pod-api/precificacao endpoint (production cost per print run) is wired
in behind a switch; it degrades gracefully while Metabrasil finishes it.
    """,
    'author': "EdLab Press",
    'category': 'Inventory/Purchase',
    'version': '19.0.2.2.0',
    'license': 'AGPL-3',
    'depends': [
        'sale_stock',
        'purchase_stock',
        'sale_purchase',        # purchase.order.line.sale_line_id: the real SO<->PO link
        'stock_dropshipping',   # direct-to-customer print orders ride the dropship route
        'stock_delivery',       # carrier + tracking ref on the picking
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/product_pod_data.xml',
        'data/delivery_carrier_data.xml',
        'data/mail_templates.xml',
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
        'views/product_template_views.xml',
        'views/product_supplierinfo_views.xml',
        'views/purchase_order_views.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
        'views/delivery_carrier_views.xml',
        'views/choose_delivery_carrier_views.xml',
    ],
    'installable': True,
    'application': False,
}
