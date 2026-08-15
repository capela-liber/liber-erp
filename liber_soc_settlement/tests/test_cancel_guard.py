# -*- coding: utf-8 -*-
"""A consignment operation that was run cannot be cancelled.

'confirmed' is written in exactly one place: inside action_run, which validates
the delivery picking in the same call. So a confirmed CO always means the shelf
was already debited and the sale already exists.

Cancelling one used to cascade over the sale, the remessa and the devolucao and
then skip any picking already 'done' -- the books stayed off the customer's
shelf with no sale behind them, and the chatter listed only what HAD been
cancelled, so the hole was invisible. The button had no confirm= either: one
click, from a screen where it sat next to Run.
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCancelGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.team = cls.env['crm.team'].create({'name': 'Guard'})
        cls.product = cls.env['product.product'].create({
            'name': 'Livro do Cancelamento', 'type': 'consu', 'is_storable': True})

    def _agreement(self):
        partner = self.env['res.partner'].create({
            'name': 'Livraria da Guarda', 'is_company': True})
        agr = self.env['consignment.agreement'].create({
            'partner_id': partner.id, 'company_id': self.company.id,
            'team_id': self.team.id,
            'date_start': fields.Date.today() - timedelta(days=1),
        })
        agr.action_activate()
        return agr

    def test_draft_can_still_be_cancelled(self):
        """An operation opened by mistake must still have a way out."""
        agr = self._agreement()
        st = self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id})
        self.assertEqual(st.state, 'draft')

        st.action_cancel()

        self.assertEqual(st.state, 'cancel')

    def test_confirmed_cannot_be_cancelled(self):
        """The one that matters: no cancel after the stock has left the shelf."""
        agr = self._agreement()
        st = self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id})
        # reach 'confirmed' the only way the model allows: through a Run
        st.state = 'confirmed'

        with self.assertRaises(UserError):
            st.action_cancel()

        self.assertEqual(st.state, 'confirmed', "state must not have moved")

    def test_finalized_cannot_be_cancelled_either(self):
        agr = self._agreement()
        st = self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id})
        st.state = 'done'

        with self.assertRaises(UserError):
            st.action_cancel()

    def test_one_bad_record_blocks_the_whole_call(self):
        """A multi-record cancel must not half-apply."""
        agr = self._agreement()
        ok = self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id})
        run = self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id})
        run.state = 'confirmed'

        with self.assertRaises(UserError):
            (ok | run).action_cancel()

        self.assertEqual(ok.state, 'draft',
                         "the draft one must not be cancelled on the way")
