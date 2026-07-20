# -*- coding: utf-8 -*-
{
    'name': 'Consignment - Agreements',
    'version': '19.0.2.2.0',
    'summary': 'Core consignment: agreements and the customer shelf (our stock at the customer)',
    'description': """
Consignment core (SOC redesign).

Models the *relationship* layer of consignment: an agreement per customer that
owns the "shelf" (an internal stock location holding our stock physically placed
at the customer, still ours until sold). Handles the lifecycle
(draft -> active -> suspended -> closed) and the commercial policy (settlement
cadence, replenishment policy). It does NOT move stock, invoice, or emit fiscal
documents -- those live in soc_moves / soc_settlement / soc_fiscal_br.
""",
    'author': 'EdLab Press',
    'category': 'Inventory/Consignment',
    'depends': ['base', 'mail', 'contacts', 'product', 'stock', 'sale'],
    'data': [
        'security/soc_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/consignment_agreement_views.xml',
        'views/res_partner_views.xml',
        'views/soc_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
