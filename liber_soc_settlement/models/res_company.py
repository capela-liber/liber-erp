# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # The settlement baixa (customer shelf -> customer) is the acerto sale
    # leaving the shelf. It is NOT a warehouse delivery: it does not pick from
    # our stock, it only draws down the customer's shelf. Giving it its own
    # operation type + sequence (ACERTO/, not WH/OUT/) keeps it out of the
    # warehouse's Delivery Orders and stops it reading as a pending WH job.
    # Auto-created on first use, like the shipment/return types in soc_moves.
    consignment_settlement_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Consignment Settlement Operation',
        domain="[('code', '=', 'outgoing')]",
        help="Warehouse operation type used for the settlement baixa (customer "
             "shelf -> customer): the acerto sale leaving the shelf. Kept apart "
             "from the generic delivery orders (WH/OUT).")

    def _get_consignment_settlement_operation_type(self):
        self.ensure_one()
        if not self.consignment_settlement_operation_type_id:
            self.consignment_settlement_operation_type_id = \
                self._create_consignment_operation_type(
                    _('Consignment Settlement'), 'ACERTO/%(year)s/',
                    'Consignment Settlement Operation', code='outgoing')
        return self.consignment_settlement_operation_type_id

    consignment_map_text = fields.Html(
        string='Consignment Map Text',
        help="Standard text printed at the top of the consignment map (CO) that "
             "is printed or e-mailed to the customer. Editable in the Consignment "
             "settings.")
    return_escalation_manager_id = fields.Many2one(
        'res.users', string='Return Escalation Manager',
        help="Who gets notified when a consignment return (CR) blows past its "
             "tolerable window (the last rung of the dunning ladder). Editable in "
             "the Consignment settings.")
    return_request_text = fields.Html(
        string='Return Request Text',
        help="Standard intro text of the return-request e-mail (CR) sent to the "
             "customer when a return is overdue. Editable in the Consignment "
             "settings.")
