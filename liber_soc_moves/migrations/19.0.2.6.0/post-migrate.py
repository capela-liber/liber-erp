# -*- coding: utf-8 -*-
"""COM/ e RET/ viram o padrão direcional do core (WH/OUT, WH/IN).

Até a 19.0.2.5.0 a logística da consignação dividia UMA sequence COM/ entre
a remessa ao cliente (Consignment Delivery, outgoing) e os fluxos internos de
prateleira (Consignment Shipment, internal); o retorno era RET/. O desenho
novo separa por direção, como o core faz com WH/OUT e WH/IN:

- remessa ao cliente  -> COM/OUT/%(year)s/  (a sequence compartilhada VIRA esta)
- retorno             -> COM/IN/%(year)s/   (a RET/ vira esta)
- fluxos internos     -> COM/MOV/%(year)s/  (sequence NOVA, própria)

REGRA DE FERRO: nenhum documento existente muda de nome. Esta migração só
altera ir_sequence.prefix, stock_picking_type.sequence_code e cria/reaponta a
série nova -- stock_picking.name já emitido fica exatamente como está.

Idempotente: os UPDATEs são guardados pelo prefixo antigo; re-rodar não acha
nada para mudar e não cria sequence duplicada.
"""
import logging

_logger = logging.getLogger(__name__)

OLD_SHARED_PREFIX = 'COM/%(year)s/'
OLD_RETURN_PREFIX = 'RET/%(year)s/'
NEW_OUT_PREFIX = 'COM/OUT/%(year)s/'
NEW_IN_PREFIX = 'COM/IN/%(year)s/'
NEW_MOV_PREFIX = 'COM/MOV/%(year)s/'


def _rename_sequence(cr, seq_id, old_prefix, new_prefix, company_name):
    """Rename prefix only if it still carries the old one (idempotency)."""
    cr.execute(
        "UPDATE ir_sequence SET prefix = %s "
        "WHERE id = %s AND prefix = %s RETURNING name",
        (new_prefix, seq_id, old_prefix))
    row = cr.fetchone()
    if row:
        _logger.info(
            "consignment series [%s]: ir_sequence #%s (%s): %s -> %s",
            company_name, seq_id, row[0], old_prefix, new_prefix)
        return True
    return False


def _set_sequence_code(cr, picking_type_ids, new_code, company_name):
    """SQL on purpose: writing sequence_code through the ORM makes stock
    rewrite the sequence prefix to <warehouse>/<code>/, which is exactly
    what must NOT happen here."""
    if not picking_type_ids:
        return
    cr.execute(
        "UPDATE stock_picking_type SET sequence_code = %s "
        "WHERE id IN %s AND sequence_code != %s "
        "RETURNING id, name->>'en_US'",  # picking type name is translated jsonb
        (new_code, tuple(picking_type_ids), new_code))
    for pt_id, name in cr.fetchall():
        _logger.info(
            "consignment series [%s]: picking type #%s (%s): "
            "sequence_code -> %s", company_name, pt_id, name, new_code)


def migrate(cr, version):
    cr.execute("""
        SELECT c.id, p.name,
               c.consignment_shipment_operation_type_id,
               c.consignment_return_operation_type_id,
               c.consignment_delivery_operation_type_id
          FROM res_company c
          JOIN res_partner p ON p.id = c.partner_id
         ORDER BY c.id
    """)
    for (company_id, company_name, ship_type_id, ret_type_id,
         deliv_type_id) in cr.fetchall():

        def seq_of(ptype_id):
            if not ptype_id:
                return None
            cr.execute("SELECT sequence_id FROM stock_picking_type "
                       "WHERE id = %s", (ptype_id,))
            row = cr.fetchone()
            return row and row[0]

        ship_seq = seq_of(ship_type_id)
        ret_seq = seq_of(ret_type_id)
        deliv_seq = seq_of(deliv_type_id)

        # --- retorno: RET/ vira COM/IN/ -------------------------------
        if ret_seq:
            _rename_sequence(cr, ret_seq, OLD_RETURN_PREFIX,
                             NEW_IN_PREFIX, company_name)
            _set_sequence_code(cr, [ret_type_id], 'COM/IN', company_name)

        # --- remessa ao cliente: a COM/ compartilhada vira COM/OUT/ ---
        if deliv_seq:
            _rename_sequence(cr, deliv_seq, OLD_SHARED_PREFIX,
                             NEW_OUT_PREFIX, company_name)
            _set_sequence_code(cr, [deliv_type_id], 'COM/OUT', company_name)

        # --- fluxos internos: deixam de dividir e ganham COM/MOV/ -----
        if ship_seq and deliv_seq and ship_seq == deliv_seq:
            # Every INTERNAL type still riding the (now COM/OUT) shared
            # sequence moves to a brand-new COM/MOV series.
            cr.execute(
                "SELECT id FROM stock_picking_type "
                "WHERE sequence_id = %s AND code = 'internal'", (ship_seq,))
            internal_ids = [r[0] for r in cr.fetchall()]
            if internal_ids:
                cr.execute("""
                    INSERT INTO ir_sequence
                        (name, implementation, prefix, padding,
                         number_next, number_increment, company_id, active)
                    VALUES ('Consignment Internal Moves Operation',
                            'standard', %s, 5, 1, 1, %s, true)
                    RETURNING id
                """, (NEW_MOV_PREFIX, company_id))
                new_seq_id = cr.fetchone()[0]
                cr.execute(
                    "UPDATE stock_picking_type SET sequence_id = %s "
                    "WHERE id IN %s", (new_seq_id, tuple(internal_ids)))
                _logger.info(
                    "consignment series [%s]: created ir_sequence #%s %s and "
                    "repointed internal picking types %s to it (they no "
                    "longer share the customer-facing series)",
                    company_name, new_seq_id, NEW_MOV_PREFIX, internal_ids)
                _set_sequence_code(cr, internal_ids, 'COM/MOV', company_name)
        elif ship_seq and ship_seq != deliv_seq:
            # No sharing (base where only the shelf flow ever ran, or the
            # migration already passed): the internal series just takes the
            # directional name. Guarded by the old prefix, so a re-run or a
            # base already on COM/MOV is untouched.
            if _rename_sequence(cr, ship_seq, OLD_SHARED_PREFIX,
                                NEW_MOV_PREFIX, company_name):
                _set_sequence_code(cr, [ship_type_id], 'COM/MOV',
                                   company_name)
