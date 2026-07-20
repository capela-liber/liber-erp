# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Pull the CO root out of the warehouse tree.

    Until now it was created under the warehouse's view location, so every
    consignment shelf below it was counted in the native On Hand / Forecasted.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Location = env['stock.location']
    for root in Location.search([('is_consignment_root', '=', True)]):
        if not root.location_id:
            continue
        root.location_id = False
        Location.search([('id', 'child_of', root.id)])._compute_warehouse_id()
