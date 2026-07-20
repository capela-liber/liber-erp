# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    consignment_partner_id = fields.Many2one(
        'res.partner', string='Customer', store=True, index=True,
        compute='_compute_consignment_fields',
        help="Customer whose consignment shelf this move touched. Lets the "
             "ledger group every shipment/return by customer, not just by book.")
    consignment_qty = fields.Float(
        string='Consigned Qty', store=True,
        compute='_compute_consignment_fields',
        help="Net effect on the customer's shelf: positive when goods are "
             "placed on it (shipment / replenishment), negative when they leave "
             "it (return or settled sale). Sum it over time to follow how each "
             "customer's consignment balance evolves.")
    consignment_balance = fields.Float(
        string='Running Balance', compute='_compute_consignment_balance',
        help="Consignment balance on this customer's shelf for this book right "
             "after this move: the cumulative sum of every earlier consigned "
             "quantity (+/-) plus this one, chronologically. Read the ledger "
             "oldest-to-newest to follow the shelf balance move by move.")

    @api.depends('location_id.is_consignment_shelf',
                 'location_id.consignment_partner_id',
                 'location_dest_id.is_consignment_shelf',
                 'location_dest_id.consignment_partner_id',
                 'quantity')
    def _compute_consignment_fields(self):
        for move in self:
            src, dest = move.location_id, move.location_dest_id
            partner = self.env['res.partner']
            qty = 0.0
            if dest.is_consignment_shelf:
                partner = dest.consignment_partner_id
                qty += move.quantity
            if src.is_consignment_shelf:
                partner = partner or src.consignment_partner_id
                qty -= move.quantity
            move.consignment_partner_id = partner
            move.consignment_qty = qty

    def _compute_consignment_balance(self):
        # Running balance needs every earlier shelf move for the same
        # customer+book, not just the records on screen, so we rebuild the
        # cumulative series per (customer, book) pair from the full ledger
        # universe (done moves that touched a shelf) and read each move's
        # balance from it.
        relevant = self.filtered(
            lambda m: m.consignment_partner_id and m.product_id)
        (self - relevant).consignment_balance = 0.0
        pairs = {(m.consignment_partner_id.id, m.product_id.id)
                 for m in relevant}
        balance_by_move = {}
        for partner_id, product_id in pairs:
            series = self.env['stock.move'].search(
                [('consignment_partner_id', '=', partner_id),
                 ('product_id', '=', product_id),
                 ('state', '=', 'done')],
                order='date, id')
            running = 0.0
            for mv in series:
                running += mv.consignment_qty
                balance_by_move[mv.id] = running
        for move in relevant:
            move.consignment_balance = balance_by_move.get(move.id, 0.0)
