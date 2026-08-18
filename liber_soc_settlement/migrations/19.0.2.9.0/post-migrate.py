# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Link the ACERTO/ moves of past settlements to their S lines.

    The baixa and the sale were born as strangers: the picking debited the
    shelf, but no move carried a sale_line_id, so the sale's delivered qty
    stayed at zero and -- with the catalog on "delivered quantities" -- the
    acerto could never be invoiced. New settlements are linked at creation
    (see _create_shelf_outflow); this carries the existing ones over.

    Writing sale_line_id is enough: qty_delivered and invoice_status are
    computes that depend on the move link and recompute on their own. The
    already-invoiced sales are safe -- delivered rising to meet what was
    invoiced only makes them consistent.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    settlements = env['consignment.settlement'].search([
        ('delivery_picking_id', '!=', False),
        ('sale_order_id', '!=', False),
    ])
    for settlement in settlements:
        so_lines = defaultdict(list)
        for so_line in settlement.sale_order_id.order_line:
            so_lines[so_line.product_id.id].append(so_line)
        for move in settlement.delivery_picking_id.move_ids.filtered(
                lambda m: not m.sale_line_id):
            candidates = so_lines.get(move.product_id.id)
            if not candidates:
                continue
            move.sale_line_id = (
                candidates.pop(0) if len(candidates) > 1 else candidates[0])
