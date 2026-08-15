# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    support_ticket_ids = fields.One2many(
        'liber.support.ticket', 'sale_order_id', string='Support Tickets')
    support_ticket_count = fields.Integer(
        compute='_compute_support_ticket_count')

    @api.depends('support_ticket_ids')
    def _compute_support_ticket_count(self):
        for order in self:
            order.support_ticket_count = len(order.support_ticket_ids)

    def action_view_support_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'liber_support.action_support_ticket')
        action['domain'] = [('sale_order_id', '=', self.id)]
        action['context'] = {
            'default_sale_order_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_company_id': self.company_id.id,
            'default_channel': 'manual',
        }
        return action

    def action_open_support_ticket(self):
        """The seller registers a conversation that started on the phone:
        a ticket born already glued to partner, company and order."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'liber.support.ticket',
            'view_mode': 'form',
            'context': {
                'default_sale_order_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_company_id': self.company_id.id,
                'default_name': self.name,
                'default_channel': 'manual',
            },
        }
