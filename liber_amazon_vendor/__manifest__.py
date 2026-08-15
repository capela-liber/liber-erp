# -*- coding: utf-8 -*-
{
    'name': 'Amazon Vendor Central',
    'version': '19.0.1.3.0',
    'summary': 'Read purchase orders from Amazon Vendor Central and turn '
               'them into quotations — read-only towards Amazon',
    'description': """
The Amazon side of the house, and only the reading half.

In Vendor Central **Amazon is the buyer**. What the SP-API calls a
`purchaseOrder` is Amazon's order, which on our side is a sale — so what this
module produces is a quotation, never a purchase order. Getting that backwards
inverts stock and invoicing.

What it does: reads the purchase orders, mirrors them, matches each ISBN
against the product barcode, and lets a person turn a mirrored order into a
draft quotation.

What it deliberately does not do: acknowledge orders, send ASNs, print carton
labels, or invoice through EDI. Those carry an Amazon SLA and belong to a
person watching a clock, not to a cron. The API layer here has no write path
at all, and a test enforces it.

Because Amazon changes an order after it was created — states move, accepted
quantities differ from ordered ones — every import re-reads a window instead
of walking a watermark forward. When a re-read finds a change to an order that
already produced a quotation, the module flags it and rewrites nothing: the
document belongs to whoever made it.

No new Python dependency: since 2023 the SP-API needs no AWS SigV4 signature,
so `requests` is the whole client.
""",
    'author': 'EdLab Press',
    'website': 'https://github.com/capela-liber/liber-erp',
    'category': 'Sales/Sales',
    'depends': ['sale', 'product', 'mail', 'base_setup'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/liber_amazon_security.xml',
        'security/ir.model.access.csv',
        'data/amazon_cron.xml',
        'views/amazon_account_views.xml',
        'views/amazon_unit_views.xml',
        # antes das views: a lista de pedidos referencia a ação
        # do assistente no botão de cabeçalho.
        'wizard/amazon_import_views.xml',
        'views/amazon_order_views.xml',
        'views/amazon_schedule_views.xml',
        'views/amazon_title_views.xml',
        'views/res_config_settings_views.xml',
        # por último: a ponte precisa dos grupos deste módulo já carregados
        'data/liber_roles_bridge.xml',
        'views/amazon_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'AGPL-3',
}
