# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ConsignmentSettlement(models.Model):
    _inherit = 'consignment.settlement'

    support_ticket_ids = fields.One2many(
        'liber.support.ticket', 'settlement_id',
        string='Support Tickets')
    support_ticket_count = fields.Integer(
        compute='_compute_support_ticket_count')

    @api.depends('support_ticket_ids')
    def _compute_support_ticket_count(self):
        for settlement in self:
            settlement.support_ticket_count = len(
                settlement.support_ticket_ids)

    def action_view_support_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'liber_support.action_support_ticket')
        action['domain'] = [('settlement_id', '=', self.id)]
        action['context'] = {
            'default_settlement_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_company_id': self.company_id.id,
            'default_kind': 'consignment',
            'default_channel': 'manual',
        }
        return action
