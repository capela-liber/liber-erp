# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    consignment_partner_id = fields.Many2one(
        'res.partner', string='Customer', store=True,
        related='location_id.consignment_partner_id',
        help="Customer whose consignment shelf holds this stock.")
    consignment_team_id = fields.Many2one(
        'crm.team', string='Sales Channel',
        compute='_compute_consignment_team_id', store=True, index=True,
        help="The channel this shelf belongs to, read from the agreement that "
             "owns it. This is the axis the campaigns work on, so it has to be "
             "the axis this report can be read on.")

    @api.depends('location_id')
    def _compute_consignment_team_id(self):
        """The channel comes from the AGREEMENT, which owns the shelf location.

        Not from the partner: res.partner.team_id no longer exists in Odoo 19, and
        going through the agreement is the more honest route anyway -- the same
        customer can hold shelves under different contracts, on different channels.
        """
        Agreement = self.env['consignment.agreement']
        shelves = self.location_id.filtered('is_consignment_shelf')
        by_location = {}
        if shelves:
            for agreement in Agreement.search([('location_id', 'in', shelves.ids)]):
                by_location.setdefault(agreement.location_id.id, agreement.team_id)
        for quant in self:
            quant.consignment_team_id = by_location.get(quant.location_id.id, False)
