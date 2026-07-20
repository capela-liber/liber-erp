# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'soc_shortfall')
class TestShortfall(TransactionCase):
    """The four natures of a ruptura, and the coverage that predicts them.

    Each nature is one distinct way a campaign target goes unmet, and each one
    must be recorded apart from the others -- lumping them together is exactly
    the blindness this feature removes.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.supplier_loc = cls.env.ref('stock.stock_location_suppliers')
        cls.team = cls.env['crm.team'].create({'name': 'Escolar'})
        cls.product = cls.env['product.product'].create({
            'name': 'Dom Casmurro', 'type': 'consu', 'is_storable': True})

    # -- helpers ------------------------------------------------------------
    def _set_wh_stock(self, product, qty):
        self.env['stock.quant']._update_available_quantity(
            product, self.stock_loc, qty)

    def _add_incoming(self, product, qty):
        """A confirmed inbound move: bumps incoming_qty (the forecast)."""
        move = self.env['stock.move'].create({
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom': product.uom_id.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'company_id': self.company.id,
        })
        move._action_confirm()
        return move

    def _agreement(self, name, days_ago_start=0):
        partner = self.env['res.partner'].create({
            'name': name, 'is_company': True})
        agr = self.env['consignment.agreement'].create({
            'partner_id': partner.id, 'company_id': self.company.id,
            'team_id': self.team.id,
            'date_start': fields.Date.today() - timedelta(days=days_ago_start),
        })
        agr.action_activate()
        return agr

    def _campaign(self, target, product=None, running=True):
        return self.env['consignment.template'].create({
            'name': 'SEED test',
            'team_id': self.team.id,
            'date_start': fields.Date.today() - timedelta(days=5),
            'date_end': fields.Date.today() + timedelta(days=30) if running else
                        fields.Date.today() - timedelta(days=1),
            'line_ids': [(0, 0, {
                'product_id': (product or self.product).id,
                'product_uom_qty': target})],
        })

    def _draft_settlement(self, agr, campaigns=None):
        st = self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id})
        if campaigns is not None:
            st.campaign_ids = [(6, 0, campaigns.ids)]
        return st

    # -- stock facts --------------------------------------------------------
    def test_stock_facts_on_hand_and_incoming(self):
        self._set_wh_stock(self.product, 30)
        self._add_incoming(self.product, 20)
        facts = self.env['consignment.shortfall']._stock_facts(
            self.company, self.product)
        self.assertEqual(facts[self.product.id]['on_hand'], 30)
        self.assertEqual(facts[self.product.id]['incoming'], 20)

    def test_owning_campaign_highest_target_wins(self):
        low = self._campaign(5)
        high = self._campaign(12)
        owner = self.env['consignment.shortfall']._owning_campaign(
            low | high, self.product)
        self.assertEqual(owner, high)

    # -- coverage -----------------------------------------------------------
    def test_coverage_balances_target_across_shelves(self):
        for i in range(3):
            self._agreement('Loja %s' % i)
        self._set_wh_stock(self.product, 25)
        campaign = self._campaign(10)
        line = campaign.line_ids
        # 3 shelves x target 10 = 30 needed; 25 on hand, 0 inbound.
        self.assertEqual(line.coverage_shelves, 3)
        self.assertEqual(line.coverage_needed, 30)
        self.assertEqual(line.coverage_on_hand, 25)
        self.assertEqual(line.coverage_short, 5)
        self.assertEqual(line.coverage_shelves_served, 2)  # 25 // 10
        self.assertAlmostEqual(line.coverage_pct, 25 / 30 * 100)

    def test_coverage_nets_inbound_forecast(self):
        self._agreement('Loja')
        self._set_wh_stock(self.product, 4)
        self._add_incoming(self.product, 10)
        campaign = self._campaign(10)
        # 1 shelf, need 10; 4 on hand + 10 inbound = 14 -> nothing will short.
        self.assertEqual(campaign.line_ids.coverage_short, 0)

    # -- nature: estoque ----------------------------------------------------
    def test_estoque_is_net_of_forecast(self):
        agr = self._agreement('Loja')
        self._set_wh_stock(self.product, 10)
        self._add_incoming(self.product, 5)
        campaign = self._campaign(40)
        st = self._draft_settlement(agr, campaigns=campaign)
        line = self.env['consignment.settlement.line'].create({
            'settlement_id': st.id, 'product_id': self.product.id,
            'qty_target': 40, 'qty_reported': 0})
        st._record_shortfalls()
        rows = self.env['consignment.shortfall'].search([
            ('settlement_id', '=', st.id)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.nature, 'estoque')
        # needed 40, on hand 10 + inbound 5 = 15 -> short 25 (not 30).
        self.assertEqual(rows.qty_short, 25)
        self.assertEqual(rows.campaign_id, campaign)

    # -- nature: manual -----------------------------------------------------
    def test_manual_when_operator_sends_less_than_stock_allows(self):
        agr = self._agreement('Loja')
        self._set_wh_stock(self.product, 100)  # plenty
        campaign = self._campaign(40)
        st = self._draft_settlement(agr, campaigns=campaign)
        line = self.env['consignment.settlement.line'].create({
            'settlement_id': st.id, 'product_id': self.product.id,
            'qty_target': 40, 'qty_reported': 0})
        line.qty_replenish = 15  # operator overrides down
        # Mirror action_run's order exactly: the freeze must NOT revert the edit.
        line._freeze_map()
        st._record_shortfalls()
        rows = self.env['consignment.shortfall'].search([
            ('settlement_id', '=', st.id)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.nature, 'manual')
        self.assertEqual(rows.qty_short, 25)  # min(40,100) - 15

    def test_manual_send_survives_freeze_and_confirm(self):
        """The operator's manual send is a decision, not a suggestion: neither
        the frozen map nor confirming the operation may revert it."""
        agr = self._agreement('Loja')
        self._set_wh_stock(self.product, 100)
        campaign = self._campaign(40)
        st = self._draft_settlement(agr, campaigns=campaign)
        line = self.env['consignment.settlement.line'].create({
            'settlement_id': st.id, 'product_id': self.product.id,
            'qty_target': 40, 'qty_reported': 0})
        line.qty_replenish = 15
        line._freeze_map()
        self.assertEqual(line.qty_replenish, 15)  # freeze did not revert it
        st.state = 'confirmed'
        self.assertEqual(line.qty_replenish, 15)  # nor did leaving draft

    # -- nature: falta ------------------------------------------------------
    def test_falta_when_running_campaign_not_applied(self):
        agr = self._agreement('Loja')
        self.env['stock.quant']._update_available_quantity(
            self.product, agr.location_id, 3)  # 3 already on the shelf
        self._campaign(10)  # running, but NOT applied to the settlement below
        st = self._draft_settlement(agr, campaigns=self.env['consignment.template'])
        st._record_shortfalls()
        rows = self.env['consignment.shortfall'].search([
            ('settlement_id', '=', st.id)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.nature, 'falta')
        self.assertEqual(rows.qty_short, 7)  # target 10 - 3 on shelf

    def test_applied_campaign_raises_no_falta(self):
        agr = self._agreement('Loja')
        self._set_wh_stock(self.product, 100)
        campaign = self._campaign(10)
        st = self._draft_settlement(agr, campaigns=campaign)
        self.env['consignment.settlement.line'].create({
            'settlement_id': st.id, 'product_id': self.product.id,
            'qty_target': 10, 'qty_reported': 0})
        st._record_shortfalls()
        self.assertFalse(self.env['consignment.shortfall'].search([
            ('settlement_id', '=', st.id), ('nature', '=', 'falta')]))

    # -- nature: tempo (cron) ----------------------------------------------
    def test_tempo_cron_flags_overdue_customer(self):
        agr = self._agreement('Loja', days_ago_start=60)  # never settled
        self.env['stock.quant']._update_available_quantity(
            self.product, agr.location_id, 2)
        campaign = self._campaign(10)
        self.env['consignment.template']._cron_flag_overdue()
        rows = self.env['consignment.shortfall'].search([
            ('nature', '=', 'tempo'), ('campaign_id', '=', campaign.id)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.partner_id, agr.partner_id)
        self.assertEqual(rows.qty_short, 8)  # 10 target - 2 on shelf
        # Idempotent: running again does not accumulate.
        self.env['consignment.template']._cron_flag_overdue()
        self.assertEqual(1, self.env['consignment.shortfall'].search_count([
            ('nature', '=', 'tempo'), ('campaign_id', '=', campaign.id)]))

    def test_tempo_clears_when_recently_settled(self):
        agr = self._agreement('Loja', days_ago_start=60)
        self.env['stock.quant']._update_available_quantity(
            self.product, agr.location_id, 2)
        campaign = self._campaign(10)
        self.env['consignment.template']._cron_flag_overdue()
        self.assertTrue(self.env['consignment.shortfall'].search([
            ('nature', '=', 'tempo'), ('campaign_id', '=', campaign.id)]))
        # A fresh acerto within the window: the customer is no longer overdue.
        self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id,
            'date': fields.Date.today(), 'state': 'confirmed'})
        self.env['consignment.template']._cron_flag_overdue()
        self.assertFalse(self.env['consignment.shortfall'].search([
            ('nature', '=', 'tempo'), ('campaign_id', '=', campaign.id)]))

    # -- re-run is idempotent ----------------------------------------------
    def test_rerun_rewrites_settlement_rows(self):
        agr = self._agreement('Loja')
        self._set_wh_stock(self.product, 10)
        campaign = self._campaign(40)
        st = self._draft_settlement(agr, campaigns=campaign)
        self.env['consignment.settlement.line'].create({
            'settlement_id': st.id, 'product_id': self.product.id,
            'qty_target': 40, 'qty_reported': 0})
        st._record_shortfalls()
        st._record_shortfalls()  # twice
        self.assertEqual(1, self.env['consignment.shortfall'].search_count([
            ('settlement_id', '=', st.id)]))

    # -- a blank line must not crash the recent-sales compute --------------
    def test_blank_line_does_not_crash_recent_sales(self):
        """A line with no product yet -- the empty row the form creates before a
        product is picked -- must not blow up qty_recent_sales. Its False product
        id is never among the looked-up products, so the fiscal-facts dict has no
        key for it. Regression for xml[False] KeyError in _compute_qty_recent_sales.
        """
        agr = self._agreement('Livraria Sem Produto')
        st = self._draft_settlement(agr)
        # .new() (not create) because product_id is required: this is exactly the
        # transient, product-less line the onchange computes over in the form.
        line = self.env['consignment.settlement.line'].new({
            'settlement_id': st.id})
        self.assertFalse(line.product_id)
        # reading the computed field runs _compute_qty_recent_sales on the line
        self.assertEqual(line.qty_recent_sales, 0)
        self.assertFalse(line.sale_order_ids)
