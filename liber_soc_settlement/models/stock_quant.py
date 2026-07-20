# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models


class StockQuant(models.Model):
    """The age of what is sitting on a customer's shelf.

    Same rule as the CO line (see consignment.settlement.line._shelf_anchors):
    the clock starts at the last acerto for this customer -- settled in Odoo, or
    only present as an imported NFe -- and, for a title never settled, at the
    moment it hit the shelf. The rule is SHARED, not copied: two copies would
    drift and the same title would show two different ages in two reports.

    STORED, unlike on the CO line, and here is why: the On Shelf report is a
    plain list, so Odoo sorts and filters it in SQL. A computed non-stored field
    has no column to sort by -- the whole point of showing the age here is to put
    the most overdue titles on top. The price is that the value goes stale by one
    day every night, so a daily cron recomputes it (the number changes on its own
    even when nothing moves, which is exactly why no dependency can catch it).
    """
    _inherit = 'stock.quant'

    last_settlement_date = fields.Date(
        string='Last Settlement', compute='_compute_shelf_age', store=True,
        help="Date of the most recent acerto of this title for this customer. "
             "Never settled: when it hit the shelf.")
    days_since_settlement = fields.Integer(
        string='Days', compute='_compute_shelf_age', store=True,
        help="Days this title has been sitting on the customer's shelf without "
             "an acerto. Refreshed every morning.")
    shelf_status = fields.Selection([
        ('ok', 'Ok'),
        ('attention', 'Attention'),
        ('critical', 'Critical'),
        ('no_return', 'No Return'),
    ], string='Shelf Status', compute='_compute_shelf_age', store=True,
        help="Ok / Attention / Critical / No Return by days without an acerto. "
             "Thresholds in the Consignment settings.")

    qty_target = fields.Integer(
        string='Target', compute='_compute_qty_target', store=True,
        help="How many copies of this title the running campaigns of this "
             "customer's channel ask for -- the shelf's goal, beside what is "
             "actually on hand. Highest target wins when campaigns overlap, the "
             "same rule the acerto applies. Refreshed every morning: a campaign "
             "starting or ending changes it with no write on the quant to notice.")

    @api.depends('consignment_partner_id', 'consignment_team_id', 'product_id')
    def _compute_qty_target(self):
        """The target assortment overlaid on the shelf, per (channel, title).

        Same source and same HIGHEST-TARGET-WINS rule as the acerto (see
        consignment.settlement._running_campaigns / action_apply_campaigns): the
        running campaigns of the customer's channel, max per title. STORED so the
        Inventory pivot can measure it against On Hand -- a non-stored field has
        no column to aggregate.
        """
        self.qty_target = 0
        teams = self.consignment_team_id
        if not teams:
            return
        campaigns = self.env['consignment.template'].search([
            ('is_running', '=', True), ('team_id', 'in', teams.ids)])
        # {(team_id, product_id): highest target across running campaigns}
        target_map = {}
        for campaign in campaigns:
            team_id = campaign.team_id.id
            for line in campaign.line_ids:
                key = (team_id, line.product_id.id)
                target_map[key] = max(target_map.get(key, 0), line.product_uom_qty)
        for quant in self:
            quant.qty_target = target_map.get(
                (quant.consignment_team_id.id, quant.product_id.id), 0)

    @api.depends('product_id', 'location_id', 'quantity')
    def _compute_shelf_age(self):
        Line = self.env['consignment.settlement.line']
        thresholds = Line._shelf_thresholds()
        today = fields.Date.context_today(self)
        self.last_settlement_date = False
        self.days_since_settlement = 0
        self.shelf_status = False
        # One anchor lookup per (customer, company, shelf), not per quant.
        groups = defaultdict(lambda: self.env['stock.quant'])
        for quant in self:
            if quant.location_id.is_consignment_shelf and quant.consignment_partner_id:
                groups[(quant.consignment_partner_id,
                        quant.company_id or self.env.company,
                        quant.location_id)] |= quant
        for (partner, company, shelf), quants in groups.items():
            anchors = Line._shelf_anchors(
                partner, company, shelf, quants.product_id.ids)
            for quant in quants:
                anchor = anchors.get(quant.product_id.id)
                if not anchor:
                    continue
                days = (today - anchor).days
                quant.last_settlement_date = anchor
                quant.days_since_settlement = days
                quant.shelf_status = Line._shelf_bucket(days, thresholds)

    @api.model
    def _cron_refresh_shelf_age(self):
        """The age grows by itself, and a campaign's window opens and closes by
        the calendar: no write on the quant can trigger either recompute, so both
        are refreshed on a clock instead."""
        quants = self.search([
            ('location_id.is_consignment_shelf', '=', True),
            ('quantity', '!=', 0),
        ])
        for fname in ('last_settlement_date', 'days_since_settlement',
                      'shelf_status', 'qty_target'):
            self.env.add_to_compute(self._fields[fname], quants)
        quants.flush_recordset()
        return len(quants)
