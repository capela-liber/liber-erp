# -*- coding: utf-8 -*-
"""The directional consignment series (COM/OUT, COM/MOV, COM/IN).

Two promises under test:

1. A NEW base is born with three separate series, mirroring the core's
   WH/OUT / WH/IN: customer-facing remessa on COM/OUT, internal shelf flows
   on their own COM/MOV (no longer sharing a sequence with the remessa),
   return on COM/IN.

2. The 19.0.2.6.0 migration takes an OLD base (shared COM/ + RET/) to the
   same layout while touching ONLY ir_sequence and sequence_code -- a
   picking already named COM/2026/xxxxx or RET/2026/xxxxx keeps its name
   forever. That is the iron rule for prod; the test builds the old state
   by hand and calls the migration function directly, twice (idempotency).
"""
import importlib.util
import os

from odoo.modules import get_module_path
from odoo.tests import TransactionCase, tagged


def _load_migration():
    path = os.path.join(get_module_path('liber_soc_moves'),
                        'migrations', '19.0.2.6.0', 'post-migrate.py')
    spec = importlib.util.spec_from_file_location('soc_series_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install', 'soc_moves')
class TestConsignmentSeries(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Reuse the db's company: res.company.create breaks under account
        # (fiscalyear_last_day NOT NULL), and the getters are per-company
        # anyway.
        cls.company = cls.env.company
        cls.deliv = cls.company._get_consignment_delivery_operation_type()
        cls.ship = cls.company._get_consignment_shipment_operation_type()
        cls.ret = cls.company._get_consignment_return_operation_type()

    def test_new_base_gets_three_directional_series(self):
        """Fresh base: COM/OUT (outgoing), COM/MOV (internal), COM/IN."""
        self.assertEqual(self.deliv.code, 'outgoing')
        self.assertEqual(self.deliv.sequence_id.prefix, 'COM/OUT/%(year)s/')
        self.assertEqual(self.deliv.sequence_code, 'COM/OUT')
        self.assertEqual(self.ship.code, 'internal')
        self.assertEqual(self.ship.sequence_id.prefix, 'COM/MOV/%(year)s/')
        self.assertEqual(self.ship.sequence_code, 'COM/MOV')
        self.assertEqual(self.ret.sequence_id.prefix, 'COM/IN/%(year)s/')
        self.assertEqual(self.ret.sequence_code, 'COM/IN')

    def test_internal_no_longer_shares_the_remessa_sequence(self):
        """The old design's whole point of failure: one sequence for two
        natures. Delivery and shelf flow must number independently."""
        self.assertNotEqual(self.deliv.sequence_id, self.ship.sequence_id)

    def _build_old_state(self):
        """Rewind the picking types to the pre-19.0.2.6.0 layout, by SQL --
        the same surface the migration works on."""
        cr = self.env.cr
        self.env.flush_all()
        shared_seq = self.ship.sequence_id
        cr.execute("UPDATE ir_sequence SET prefix = %s WHERE id = %s",
                   ('COM/%(year)s/', shared_seq.id))
        cr.execute("UPDATE stock_picking_type "
                   "SET sequence_id = %s, sequence_code = 'COM' "
                   "WHERE id IN %s", (shared_seq.id,
                                      (self.ship.id, self.deliv.id)))
        cr.execute("UPDATE ir_sequence SET prefix = %s WHERE id = %s",
                   ('RET/%(year)s/', self.ret.sequence_id.id))
        cr.execute("UPDATE stock_picking_type SET sequence_code = 'RET' "
                   "WHERE id = %s", (self.ret.id,))
        self.env.invalidate_all()
        return shared_seq

    def test_migration_renames_series_and_never_a_document(self):
        shared_seq = self._build_old_state()
        warehouse = self.company._consignment_warehouse()
        # Documents already issued under the old series: the iron rule says
        # their names never change.
        old_pickings = self.env['stock.picking'].create([
            {'name': 'COM/2026/99998', 'picking_type_id': self.ship.id,
             'location_id': warehouse.lot_stock_id.id,
             'location_dest_id': warehouse.lot_stock_id.id},
            {'name': 'RET/2026/99999', 'picking_type_id': self.ret.id,
             'location_id': warehouse.lot_stock_id.id,
             'location_dest_id': warehouse.lot_stock_id.id},
        ])
        self.env.flush_all()

        migration = _load_migration()
        migration.migrate(self.env.cr, '19.0.2.5.0')
        self.env.invalidate_all()

        # the shared sequence became the customer-facing COM/OUT ...
        self.assertEqual(shared_seq.prefix, 'COM/OUT/%(year)s/')
        self.assertEqual(self.deliv.sequence_id, shared_seq)
        self.assertEqual(self.deliv.sequence_code, 'COM/OUT')
        # ... the internal flow got its own brand-new COM/MOV ...
        self.assertNotEqual(self.ship.sequence_id, shared_seq)
        self.assertEqual(self.ship.sequence_id.prefix, 'COM/MOV/%(year)s/')
        self.assertEqual(self.ship.sequence_code, 'COM/MOV')
        # ... and RET/ became COM/IN, same sequence, new name.
        self.assertEqual(self.ret.sequence_id.prefix, 'COM/IN/%(year)s/')
        self.assertEqual(self.ret.sequence_code, 'COM/IN')

        # The iron rule: not one existing document renamed.
        self.assertEqual(sorted(old_pickings.mapped('name')),
                         ['COM/2026/99998', 'RET/2026/99999'])

    def test_migration_is_idempotent(self):
        self._build_old_state()
        self.env.flush_all()
        migration = _load_migration()
        migration.migrate(self.env.cr, '19.0.2.5.0')
        self.env.invalidate_all()
        mov_seq_after_first = self.ship.sequence_id

        migration.migrate(self.env.cr, '19.0.2.5.0')
        self.env.invalidate_all()

        self.assertEqual(self.ship.sequence_id, mov_seq_after_first,
                         "a re-run must not mint yet another COM/MOV")
        self.assertEqual(
            self.env['ir.sequence'].search_count(
                [('prefix', '=', 'COM/MOV/%(year)s/'),
                 ('company_id', '=', self.company.id)]),
            1, "exactly one COM/MOV sequence per company, however many runs")
        self.assertEqual(self.deliv.sequence_id.prefix, 'COM/OUT/%(year)s/')
        self.assertEqual(self.ret.sequence_id.prefix, 'COM/IN/%(year)s/')
