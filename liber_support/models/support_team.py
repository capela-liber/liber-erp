# -*- coding: utf-8 -*-
import ast

from odoo import api, fields, models

# Fallback SLA targets, in working hours — used only while the company
# default was never saved in Settings (ir.config_parameter empty).
SLA_FALLBACK = {
    'sla_response_hours_normal': 8.0,
    'sla_response_hours_urgent': 2.0,
    'sla_resolution_hours_normal': 24.0,
    'sla_resolution_hours_urgent': 8.0,
}


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

    # SLA targets, in working hours. The value LIVES on the team (the
    # calendar already lives here and each imprint may differ); Settings
    # only holds the company default a NEW team is born with. Editing the
    # default never rewrites an existing team.
    sla_response_hours_normal = fields.Float(
        string='First Response (Normal)',
        default=lambda self: self._sla_default(
            'sla_response_hours_normal'),
        help="Working hours until the first customer-visible reply, "
             "normal priority. New teams start from the company default "
             "in Settings.")
    sla_response_hours_urgent = fields.Float(
        string='First Response (Urgent)',
        default=lambda self: self._sla_default(
            'sla_response_hours_urgent'),
        help="Working hours until the first customer-visible reply, "
             "urgent priority. New teams start from the company default "
             "in Settings.")
    sla_resolution_hours_normal = fields.Float(
        string='Resolution (Normal)',
        default=lambda self: self._sla_default(
            'sla_resolution_hours_normal'),
        help="Working hours until closing, normal priority. 24 working "
             "hours = 3 working days of 8 hours. New teams start from "
             "the company default in Settings.")
    sla_resolution_hours_urgent = fields.Float(
        string='Resolution (Urgent)',
        default=lambda self: self._sla_default(
            'sla_resolution_hours_urgent'),
        help="Working hours until closing, urgent priority. New teams "
             "start from the company default in Settings.")

    @api.model
    def _sla_default(self, field_name):
        """Company default from Settings, or the shipped fallback while
        no default was ever saved (get_param returns False then)."""
        param = self.env['ir.config_parameter'].sudo().get_param(
            'liber_support.%s' % field_name)
        if not param:
            # get_param answers False when unset — and float(False) is
            # 0.0, not an error: guard BEFORE converting.
            return SLA_FALLBACK[field_name]
        try:
            return float(param)
        except ValueError:
            return SLA_FALLBACK[field_name]

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
