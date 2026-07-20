# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ConsignmentAgreement(models.Model):
    _inherit = 'consignment.agreement'

    settlement_ids = fields.One2many(
        'consignment.settlement', 'agreement_id', string='Settlements')
    settlement_count = fields.Integer(
        string='# Settlements', compute='_compute_settlement_count')

    def _compute_settlement_count(self):
        groups = self.env['consignment.settlement']._read_group(
            [('agreement_id', 'in', self.ids)], ['agreement_id'], ['__count'])
        counts = {agreement.id: count for agreement, count in groups}
        for agr in self:
            agr.settlement_count = counts.get(agr.id, 0)

    def action_view_settlements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlements'),
            'res_model': 'consignment.settlement',
            'view_mode': 'list,form',
            'domain': [('agreement_id', '=', self.id)],
            'context': {'default_partner_id': self.partner_id.id},
        }
