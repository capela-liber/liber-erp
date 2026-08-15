# -*- coding: utf-8 -*-
import ast

from odoo import api, fields, models


class SupportTeam(models.Model):
    """One team per mailbox. Deliberately tiny: it exists because the alias
    needs a home and because each imprint may keep its own working hours and
    SLA targets — not to grow a hierarchy."""
    _name = 'liber.support.team'
    _description = 'Support Team'
    _inherit = ['mail.alias.mixin']
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
        help="The imprint this mailbox belongs to. Incoming mail lands on "
             "this company.")
    active = fields.Boolean(default=True)
    leader_id = fields.Many2one(
        'res.users', string='Team Leader',
        help="Gets the to-do activity when a ticket goes late.")
    member_ids = fields.Many2many(
        'res.users', 'liber_support_team_users_rel', 'team_id', 'user_id',
        string='Members')
    resource_calendar_id = fields.Many2one(
        'resource.calendar', string='Working Hours',
        default=lambda self: self.env.company.resource_calendar_id,
        help="SLA deadlines are planned inside these hours — a Friday 6 PM "
             "email must not be late on Saturday.")

    # SLA targets, in working hours. On the team (not in Settings) because
    # the calendar already lives here and each imprint may differ.
    sla_response_hours_normal = fields.Float(
        string='First Response (Normal)', default=8.0)
    sla_response_hours_urgent = fields.Float(
        string='First Response (Urgent)', default=2.0)
    sla_resolution_hours_normal = fields.Float(
        string='Resolution (Normal)', default=24.0,
        help="24 working hours = 3 working days of 8 hours.")
    sla_resolution_hours_urgent = fields.Float(
        string='Resolution (Urgent)', default=8.0)

    ticket_count = fields.Integer(compute='_compute_ticket_count')

    def _compute_ticket_count(self):
        counts = dict(self.env['liber.support.ticket']._read_group(
            [('team_id', 'in', self.ids),
             ('stage_id.is_closed', '=', False)],
            ['team_id'], ['__count']))
        for team in self:
            self_count = counts.get(team, 0)
            team.ticket_count = self_count

    # ------------------------------------------------------------------
    # Alias plumbing (mirrors crm.team)
    # ------------------------------------------------------------------

    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get_id(
            'liber.support.ticket')
        # A new bookstore writes for the first time: the box must accept
        # unknown senders. The spam this lets in is triaged into the folded
        # Spam column, not bounced.
        values['alias_contact'] = 'everyone'
        if self.id:
            values['alias_defaults'] = defaults = ast.literal_eval(
                self.alias_defaults or '{}')
            defaults.update(team_id=self.id, company_id=self.company_id.id)
        return values

    def action_view_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'liber_support.action_support_ticket')
        action['domain'] = [('team_id', '=', self.id)]
        action['context'] = {'default_team_id': self.id,
                             'default_company_id': self.company_id.id,
                             'search_default_open': 1}
        return action
