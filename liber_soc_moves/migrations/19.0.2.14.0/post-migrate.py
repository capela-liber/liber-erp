# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

FIELDS = [
    'consignment_shipment_operation_type_id',
    'consignment_return_operation_type_id',
    'consignment_delivery_operation_type_id',
]


def migrate(cr, version):
    """Archive consignment operation types duplicated by a get-or-create race.

    `_get_consignment_*_operation_type()` on res.company creates its
    stock.picking.type on first use, guarded only by "if the field is
    empty" -- no row lock, no unique constraint. Two "Liberar para
    Logística" clicks close enough together, each in its own uncommitted
    transaction, both read the field as empty and each creates its OWN
    type + ir.sequence, same company, same sequence_code. Whichever
    transaction commits last "wins" the res.company pointer; the other
    type stays active, orphaned, and duplicates the card on the
    Inventory Overview.

    Caught on Edlab Press in prod (2026-09-17, via
    scripts/censo_series_consignacao.sql): two active "Retorno de
    Consignação" (sequence_code COM/IN), #357 (2 real pickings,
    COM/IN/00001-02) and #376 (8 real pickings, COM/IN/00003-10) -- #376
    is the one res_company.consignment_return_operation_type_id kept.

    Same shape, same fix as 19.0.2.7.0 (Consignment Shipment): archive
    the loser, touch nothing else. Every stock.picking already emitted
    keeps its name and its picking_type_id forever -- archiving a type
    only hides it from the Inventory Overview and from new creations.
    The race itself is closed in code
    (_lock_and_get_consignment_operation_type, row lock on res.company).

    Only acts when exactly one candidate in the duplicate group matches
    the res.company field -- anything else is a shape this migration
    hasn't seen, and it is safer to log and leave it for a human.
    """
    cr.execute("""
        SELECT c.id, p.name,
               c.consignment_shipment_operation_type_id,
               c.consignment_return_operation_type_id,
               c.consignment_delivery_operation_type_id
          FROM res_company c
          JOIN res_partner p ON p.id = c.partner_id
         ORDER BY c.id
    """)
    for row in cr.fetchall():
        company_id, company_name = row[0], row[1]
        canonical_ids = {v for v in row[2:] if v}

        cr.execute("""
            SELECT id, sequence_code FROM stock_picking_type
             WHERE company_id = %s AND active
               AND sequence_code IN ('COM/IN', 'COM/OUT', 'COM/MOV')
        """, (company_id,))
        by_code = {}
        for ptype_id, seq_code in cr.fetchall():
            by_code.setdefault(seq_code, []).append(ptype_id)

        for seq_code, ptype_ids in by_code.items():
            if len(ptype_ids) <= 1:
                continue
            kept = [i for i in ptype_ids if i in canonical_ids]
            if len(kept) != 1:
                _logger.warning(
                    "consignment operation types [%s/%s]: %s active types, "
                    "%s match a res.company field -- skipping, needs a "
                    "human look", company_name, seq_code, ptype_ids, kept)
                continue
            losers = [i for i in ptype_ids if i not in kept]
            cr.execute(
                "UPDATE stock_picking_type SET active = false "
                "WHERE id IN %s", (tuple(losers),))
            _logger.info(
                "consignment operation types [%s/%s]: archived %s (kept "
                "%s, referenced by res.company) -- duplicate born from a "
                "get-or-create race", company_name, seq_code, losers, kept)
