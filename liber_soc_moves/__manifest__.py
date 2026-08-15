# -*- coding: utf-8 -*-
{
    'name': 'Consignment - Movements',
    'version': '19.0.2.5.0',
    'summary': 'Consignment stock movements: shipment, replenishment, return, symbolic renewal',
    'description': """
Consignment movements (SOC redesign).

Every physical movement of consignment stock goes through a stock.picking /
stock.move -- never by writing stock.quant directly. A consignment.move wraps a
picking and carries the operation kind:

- shipment / replenishment: warehouse -> customer shelf (stock stays ours)
- return: customer shelf -> warehouse
- symbolic_renewal: no physical movement (only renews the fiscal clock; the two
  netting NF-es live in soc_fiscal_br)

It does NOT invoice or sell -- turning consignment into a sale happens only at
settlement (soc_settlement).
""",
    'author': 'EdLab Press',
    'category': 'Inventory/Consignment',
    # 'sale' is declared explicitly (not only via soc_agreements) because this
    # module directly extends sale.order / sale.report and overrides sale's own
    # window actions. Declaring the base we override guarantees 'sale' always
    # loads first and our overrides always apply last -- regardless of install
    # order, and it survives soc_agreements ever dropping the dependency.
    # 'stock' is declared explicitly (it already arrives via soc_agreements)
    # because security/ir.model.access.csv now hands out rights ON stock's own
    # models: an ACL that names a model of a module we do not declare would
    # break the day that dependency moved.
    'depends': ['liber_soc_agreements', 'sale', 'stock'],
    'data': [
        'security/soc_moves_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/consignment_template_views.xml',
        'views/consignment_move_views.xml',
        'views/sale_order_views.xml',
        'views/consignment_agreement_views.xml',
        'views/consigned_stock_views.xml',
        'views/product_template_views.xml',
        'views/soc_moves_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_soc_moves/static/src/js/soc_consignment_tour.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
