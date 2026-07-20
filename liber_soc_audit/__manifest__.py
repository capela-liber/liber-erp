# -*- coding: utf-8 -*-
{
    'name': 'Consignment - Audit (XML vs Map)',
    'version': '19.0.2.2.0',
    'summary': 'Rebuild the expected shelf balance from the fiscal truth (NFe XMLs) '
               'and reconcile it against the map',
    'description': """
Consignment audit (SOC redesign).

The inverse of the day-to-day settlement flow. Instead of maintaining the map
incrementally through settlements, this module *reconstructs* the expected
on-shelf balance for a customer from the fiscal truth -- every consignment NFe
(shipment, sale, return) since the beginning of the series -- and confronts it
with the current map, or *initialises* the map when none exists.

Per product, driven by CFOP:

    expected = SUM(shipments 5917/6917)
             - SUM(effective sales 5114/6114)
             - SUM(returns 5918/5919...)
             (cancelled NFes excluded; is_cancelled)
    diff = expected (fiscal) - qty_on_shelf (map)

Accepting a difference -- item by item or in toto (all-fiscal / all-map) --
generates a consignment.move of the new ``adjustment`` kind that brings the
shelf to the accepted quantity through a real inventory movement (so the
correction lives in the stock history), routing the value difference to a
configurable "Consignment Adjustment" account (Settings).

The reconciliation engine reads the already-parsed nfe.xml.panel / nfe.xml.items
records -- it never re-parses the XML.
""",
    'author': 'EdLab Press',
    'category': 'Inventory/Consignment',
    'depends': ['liber_soc_settlement', 'liber_nfe_xml', 'liber_soc_fiscal_br'],
    'data': [
        'security/soc_audit_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/nfe_cfop_consignment_data.xml',
        'views/nfe_cfop_views.xml',
        'views/consignment_audit_views.xml',
        'views/res_config_settings_views.xml',
        'views/soc_audit_menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
