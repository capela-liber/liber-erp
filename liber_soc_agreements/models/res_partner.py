# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    allow_consignment = fields.Boolean(string='Allows Consignment')
    consignment_location_id = fields.Many2one(
        'stock.location', string='Consignment Shelf',
        help="Internal location holding our stock placed at this customer.")
    consignment_agreement_ids = fields.One2many(
        'consignment.agreement', 'partner_id', string='Consignment Agreements')
    consignment_agreement_count = fields.Integer(
        string='# Consignment Agreements',
        compute='_compute_consignment_agreement_count')

    def _compute_consignment_agreement_count(self):
        groups = self.env['consignment.agreement']._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'])
        counts = {partner.id: count for partner, count in groups}
        for partner in self:
            partner.consignment_agreement_count = counts.get(partner.id, 0)

    def action_view_consignment_agreements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consignment Agreements'),
            'res_model': 'consignment.agreement',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
