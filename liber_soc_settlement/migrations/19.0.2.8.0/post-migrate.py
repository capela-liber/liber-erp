# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Take the ACERTO operation type off the Inventory Overview.

    The type is now born archived (see res_company), but the bases that already
    ran an acerto carry an active one, and it is exactly the card the commercial
    team was looking at. Archiving it here does not touch a single transfer: the
    ACERTO/ pickings keep their name, their numbering and their state.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    operation_types = env['res.company'].search([]).mapped(
        'consignment_settlement_operation_type_id')
    operation_types.filtered('active').active = False
