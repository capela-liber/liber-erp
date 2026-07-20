# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models


class ConsignmentShortfall(models.Model):
    """Ruptura, with a cause.

    "Faltou" used to mean one single thing: the warehouse did not have the book.
    But a campaign target can go unmet for reasons that have nothing to do with
    the warehouse, and lumping them together hides the ones a manager can act on:

    - ``estoque``  the shelf needed copies we do not have -- AND will not have:
                   the gap is measured net of what is already inbound (forecast),
                   so a title arriving on a PO next week is not a rupture.
    - ``manual``   we HAD the stock, but the operator sent less than the target
                   needed. Nothing was wrong with the warehouse; a person decided.
    - ``falta``    a campaign was running on the customer's channel and the
                   operation was run WITHOUT applying it. The target was never
                   even asked for.
    - ``tempo``    nobody ran an acerto for this customer in longer than the
                   tolerated window, so a running campaign's target quietly
                   stopped being pursued. Detected by a clock, not by an event.

    Each row is one (nature, customer, title) miss, with the axes the manager
    always ends up asking for: channel, campaign, operation, month. A measure
    without axes answers nothing -- that was the whole reason the old single
    number on the campaign was useless.

    Rows tied to an operation (estoque / manual / falta) are rewritten whenever
    that operation is (re-)run: the operation OWNS its rupture, so re-running it
    must never leave a stale ghost behind. The ``tempo`` rows have no operation
    to own them; the nightly cron keeps them current and clears them the moment
    the customer is settled again.
    """
    _name = 'consignment.shortfall'
    _description = 'Consignment Shortfall (Ruptura)'
    _order = 'date desc, qty_short desc, id desc'

    NATURES = [
        ('estoque', 'Estoque'),   # no copies, and none inbound
        ('manual', 'Manual'),     # had stock, operator sent less
        ('falta', 'Falta'),       # running campaign never applied
        ('tempo', 'Tempo'),       # no acerto within the tolerated window
    ]

    nature = fields.Selection(
        NATURES, string='Nature', required=True, index=True,
        help="Why the target was not met. Out of Stock: no copies and none "
             "inbound. Manual: we had stock, the operator sent less. Campaign "
             "Skipped: a running campaign was not applied to the operation. "
             "Overdue: no acerto for this customer within the tolerated window.")
    date = fields.Date(
        string='Date', required=True, index=True,
        default=fields.Date.context_today)
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, index=True,
        ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', string='Title', required=True, index=True,
        ondelete='cascade')
    team_id = fields.Many2one(
        'crm.team', string='Sales Channel', index=True)
    campaign_id = fields.Many2one(
        'consignment.template', string='Campaign', index=True, ondelete='cascade',
        help="The campaign whose target was missed. For a stock/manual miss it "
             "is the running campaign that wanted this title (highest target "
             "wins, the same rule the operation uses).")
    settlement_id = fields.Many2one(
        'consignment.settlement', string='Operation', index=True,
        ondelete='cascade',
        help="The operation this rupture happened on. Empty for Overdue: there "
             "was no operation -- that is the point.")
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)

    qty_target = fields.Integer(string='Target')
    qty_on_shelf = fields.Integer(
        string='Map', help="Stock on the customer's shelf when the miss happened.")
    qty_on_hand = fields.Integer(
        string='On Hand', help="Our warehouse stock at the time of the miss.")
    qty_incoming = fields.Integer(
        string='Inbound', help="Copies already on the way (open purchases) that "
             "were netted out of a stock rupture, so an arriving title is not "
             "counted as one.")
    qty_short = fields.Integer(
        string='Short', required=True,
        help="Copies of the target that were not placed, for this cause.")

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    @api.model
    def _owning_campaign(self, campaigns, product):
        """Which campaign a title's miss belongs to, when several want it.

        The operation resolves overlapping campaigns by HIGHEST TARGET WINS; the
        rupture must be attributed by the same rule, or the blame lands on a
        campaign that asked for less than the one that actually set the target.
        """
        best = self.env['consignment.template']
        best_target = -1
        for camp in campaigns:
            line = camp.line_ids.filtered(lambda l: l.product_id == product)
            target = max(line.mapped('product_uom_qty'), default=0)
            if line and target > best_target:
                best, best_target = camp, target
        return best

    @api.model
    def _stock_facts(self, company, products):
        """Per product: what we have now, and what is already coming.

        The single source of the two warehouse numbers every part of this
        feature needs -- the run-time rupture split and the forward coverage
        report -- so on-hand and inbound cannot drift between them. Read at the
        company's warehouse stock location, the same hard limit the operation
        ships against.
        """
        facts = {p.id: {'on_hand': 0, 'incoming': 0} for p in products}
        if not products:
            return facts
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', (company or self.env.company).id)], limit=1)
        if not warehouse:
            return facts
        located = products.with_context(location=warehouse.lot_stock_id.id)
        for product in located:
            facts[product.id] = {
                'on_hand': int(product.qty_available),
                # incoming_qty is net of what is already reserved to leave; it is
                # exactly "copies on the way that will land here".
                'incoming': int(product.incoming_qty),
            }
        return facts

    def _sync_for_settlement(self, settlement, vals_list):
        """Rewrite an operation's rupture rows: the operation owns them.

        Wipe first, then write. Re-running an operation (the overstock wizard, an
        edit-and-run-again) must reflect the LATEST decision, never accumulate a
        row per attempt.
        """
        self.search([('settlement_id', '=', settlement.id)]).unlink()
        if vals_list:
            self.create(vals_list)
