# -*- coding: utf-8 -*-
"""The ticket. Born from an email on the team alias, triaged on a kanban,
answered from the chatter. The Odoo 15 Helpdesk sins this model avoids:
the ticket is born glued to the partner and the order, the SLA is a
subtraction in working hours, and triage is dragging a card."""
import datetime

from odoo import api, fields, models, _
from odoo.tools import email_normalize

# Subject/body keyword map for the kind guess, checked in order — first hit
# wins. Drawn from the real commercial mailbox (Aug/2026 sample): "envio de
# livros" is by far the most common request.
KIND_KEYWORDS = [
    ('settlement', ('acerto', 'devolu', 'puxada')),
    ('consignment', ('consigna',)),
    ('shipment', ('envio', 'envios', 'remessa', 'frete', 'entrega',
                  'rastre', 'correio')),
    ('fiscal', ('nota fiscal', 'nf-e', 'nfe ', 'danfe', 'nota de')),
    ('billing', ('boleto', 'cobran', 'pagamento', 'fatura')),
    ('sale', ('pedido', 'compra', 'venda', 'orçamento', 'orcamento')),
    ('registration', ('cadastro', 'cnpj', 'endere')),
]

REOPEN_DAYS = 7  # customer replies within this window reopen the ticket


class SupportTicket(models.Model):
    _name = 'liber.support.ticket'
    _description = 'Support Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, id desc'
    _primary_email = 'email_from'

    number = fields.Char(
        string='Number', readonly=True, copy=False, index=True,
        default=lambda self: _('New'))
    name = fields.Char(string='Subject', required=True, tracking=True)
    email_from = fields.Char(
        string='From Email',
        help="Always kept, even when no partner could be matched.")
    partner_id = fields.Many2one(
        'res.partner', string='Partner', tracking=True,
        help="Auto-linked only when the sender email is unique in the "
             "base — a duplicated email matching the wrong partner is "
             "worse than no match.")
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company)
    team_id = fields.Many2one(
        'liber.support.team', string='Team', index=True, tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Assigned to', index=True, tracking=True,
        domain="[('share', '=', False)]",
        help="Empty means: not triaged yet.")
    stage_id = fields.Many2one(
        'liber.support.stage', string='Stage', index=True, tracking=True,
        group_expand='_read_group_stage_ids', copy=False,
        default=lambda self: self._default_stage_id())
    kind = fields.Selection([
        ('consignment', 'Consignment'),
        ('sale', 'Sale'),
        ('settlement', 'Settlement / Return'),
        ('shipment', 'Shipment'),
        ('billing', 'Billing'),
        ('fiscal', 'Fiscal / Invoice'),
        ('registration', 'Registration'),
        ('other', 'Other'),
    ], string='Kind', default='other', tracking=True)
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Urgent')], default='0', index=True,
        string='Priority')
    sale_order_id = fields.Many2one(
        'sale.order', string='Order', tracking=True,
        domain="[('partner_id', '=?', partner_id)]",
        help="The C (consignment) or S (sale) order this conversation is "
             "about.")
    tag_ids = fields.Many2many('liber.support.tag', string='Tags')
    channel = fields.Selection([
        ('email', 'Email'),
        ('manual', 'Manual'),
        ('whatsapp', 'WhatsApp'),
    ], default='manual', required=True,
        help="WhatsApp is unused today; the field exists for the day "
             "Chatwoot comes in as transport.")
    external_ref = fields.Char(
        string='External Reference',
        help="Conversation id on the external transport (e.g. Chatwoot).")
    closed_date = fields.Datetime(string='Closed on', copy=False)

    # ------------------------------------------------------------------
    # SLA — two clocks, both in working hours
    # ------------------------------------------------------------------
    sla_response_deadline = fields.Datetime(
        string='First Response Due', copy=False)
    sla_response_done = fields.Datetime(
        string='First Response At', copy=False)
    sla_resolution_deadline = fields.Datetime(
        string='Resolution Due', copy=False)
    sla_paused_since = fields.Datetime(copy=False)
    sla_resolution_remaining_hours = fields.Float(
        copy=False,
        help="Working hours left on the resolution clock, frozen when the "
             "ticket entered a pausing stage.")
    sla_state = fields.Selection([
        ('ok', 'On Time'),
        ('warn', 'Almost Due'),
        ('late', 'Late'),
        ('met', 'Met'),
        ('missed', 'Missed'),
    ], string='SLA', default='ok', copy=False, index=True)

    # ------------------------------------------------------------------
    # Defaults / helpers
    # ------------------------------------------------------------------

    @api.model
    def _default_stage_id(self):
        return self.env['liber.support.stage'].search([], limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return stages.search([])

    def _sla_calendar(self):
        self.ensure_one()
        return (self.team_id.resource_calendar_id
                or self.company_id.resource_calendar_id
                or self.env.company.resource_calendar_id)

    @staticmethod
    def _guess_kind(subject, body=''):
        """Pure function: guess the ticket kind from subject then body.
        Subject wins over body; first keyword hit wins."""
        for text in (subject or '', body or ''):
            low = text.lower()
            if not low:
                continue
            for kind, words in KIND_KEYWORDS:
                if any(w in low for w in words):
                    return kind
        return 'other'

    @api.model
    def _match_partner(self, email_from):
        """Link a partner only when the email is unique in the base.
        The 2026 commercial study found 17,044 duplicated emails; matching
        the wrong bookstore is worse than leaving the field empty."""
        email_norm = email_normalize(email_from)
        if not email_norm:
            return self.env['res.partner']
        partners = self.env['res.partner'].search(
            [('email_normalized', '=', email_norm)], limit=2)
        return partners if len(partners) == 1 else self.env['res.partner']

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('number', _('New')) == _('New'):
                vals['number'] = self.env['ir.sequence'].next_by_code(
                    'liber.support.ticket') or _('New')
            # The team decides the company, unless the caller already did.
            if vals.get('team_id') and not vals.get('company_id'):
                team = self.env['liber.support.team'].browse(
                    vals['team_id'])
                vals['company_id'] = team.company_id.id
        tickets = super().create(vals_list)
        tickets._sla_start()
        tickets._update_sla_state()
        return tickets

    def write(self, vals):
        stage_before = {t.id: t.stage_id for t in self}
        res = super().write(vals)
        if 'stage_id' in vals:
            now = fields.Datetime.now()
            for ticket in self:
                old, new = stage_before[ticket.id], ticket.stage_id
                if old == new:
                    continue
                updates = {}
                # entering a pausing stage: freeze the remaining hours
                if new.pause_sla and not old.pause_sla:
                    remaining = 0.0
                    if (ticket.sla_resolution_deadline
                            and ticket.sla_resolution_deadline > now):
                        remaining = ticket._sla_calendar()\
                            .get_work_hours_count(
                                now, ticket.sla_resolution_deadline)
                    updates.update(sla_paused_since=now,
                                   sla_resolution_remaining_hours=remaining)
                # leaving it: replant the deadline from now
                elif old.pause_sla and not new.pause_sla:
                    updates['sla_paused_since'] = False
                    if ticket.sla_resolution_remaining_hours:
                        updates['sla_resolution_deadline'] = (
                            ticket._sla_calendar().plan_hours(
                                ticket.sla_resolution_remaining_hours,
                                now, compute_leaves=True))
                        updates['sla_resolution_remaining_hours'] = 0.0
                # closing stamps the date; reopening clears it
                if new.is_closed and not old.is_closed:
                    updates['closed_date'] = now
                elif old.is_closed and not new.is_closed:
                    updates['closed_date'] = False
                if updates:
                    ticket.write(updates)
            self._update_sla_state()
        if 'priority' in vals or 'team_id' in vals:
            # Targets changed: replant both clocks from the creation date.
            self._sla_start()
            self._update_sla_state()
        return res

    # ------------------------------------------------------------------
    # SLA engine
    # ------------------------------------------------------------------

    def _sla_start(self):
        """(Re)plant both deadlines from the creation date, in working
        hours of the team calendar. Closed tickets are history: their
        clocks are never replanted (editing priority on an imported
        ticket must not resurrect a deadline)."""
        for ticket in self:
            if ticket.stage_id.is_closed:
                continue
            team = ticket.team_id
            if not team:
                ticket.sla_response_deadline = False
                ticket.sla_resolution_deadline = False
                continue
            urgent = ticket.priority == '1'
            response_h = (team.sla_response_hours_urgent if urgent
                          else team.sla_response_hours_normal)
            resolution_h = (team.sla_resolution_hours_urgent if urgent
                            else team.sla_resolution_hours_normal)
            start = ticket.create_date or fields.Datetime.now()
            cal = ticket._sla_calendar()
            ticket.sla_response_deadline = cal.plan_hours(
                response_h, start, compute_leaves=True)
            ticket.sla_resolution_deadline = cal.plan_hours(
                resolution_h, start, compute_leaves=True)

    def _update_sla_state(self):
        """One state out of two clocks: the worst pending one wins.
        Not a stored compute because it changes with the clock — the cron
        re-evaluates every 30 minutes."""
        now = fields.Datetime.now()
        for ticket in self:
            ticket.sla_state = ticket._sla_state_now(now)

    def _sla_state_now(self, now):
        self.ensure_one()
        if self.stage_id.is_closed:
            # frozen verdict: both clocks must have been met. A ticket
            # closed without a recorded first response is NOT missed if it
            # closed in time — the closing itself answered the customer.
            end = self.closed_date or now
            response_at = self.sla_response_done or end
            response_ok = (not self.sla_response_deadline
                           or response_at <= self.sla_response_deadline)
            resolution_ok = (not self.sla_resolution_deadline
                             or end <= self.sla_resolution_deadline)
            return 'met' if (response_ok and resolution_ok) else 'missed'
        if self.stage_id.pause_sla:
            # ball in the customer's court: response clock may still run
            if (self.sla_response_deadline and not self.sla_response_done
                    and now > self.sla_response_deadline):
                return 'late'
            return 'ok'
        pending = []
        if self.sla_response_deadline and not self.sla_response_done:
            pending.append(self.sla_response_deadline)
        if self.sla_resolution_deadline:
            pending.append(self.sla_resolution_deadline)
        if not pending:
            return 'ok'
        nearest = min(pending)
        if now > nearest:
            return 'late'
        start = self.create_date or now
        span = (nearest - start).total_seconds()
        if span > 0 and (now - start).total_seconds() >= 0.8 * span:
            return 'warn'
        return 'ok'

    @api.model
    def _cron_update_sla(self):
        """Every 30 minutes: refresh states and nag the team leader about
        tickets that just went late."""
        open_tickets = self.search([('stage_id.is_closed', '=', False)])
        for ticket in open_tickets:
            was_late = ticket.sla_state == 'late'
            ticket._update_sla_state()
            if ticket.sla_state == 'late' and not was_late:
                who = (ticket.user_id or ticket.team_id.leader_id
                       or self.env.user)
                ticket.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=_('SLA late: %s', ticket.number),
                    user_id=who.id)

    # ------------------------------------------------------------------
    # Mail gateway
    # ------------------------------------------------------------------

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """An email on the team alias becomes a ticket."""
        values = dict(custom_values or {})
        subject = msg_dict.get('subject') or _('No subject')
        email_from = msg_dict.get('email_from') or ''
        values.setdefault('name', subject)
        values['email_from'] = email_from
        values['channel'] = 'email'
        partner = self._match_partner(email_from)
        if partner:
            values['partner_id'] = partner.id
        values.setdefault('kind', self._guess_kind(
            subject, msg_dict.get('body') or ''))
        return super().message_new(msg_dict, custom_values=values)

    def message_update(self, msg_dict, update_vals=None):
        """A reply on an existing thread. If the ticket was waiting on the
        customer, the ball came back; if it was closed, reopen it (with a
        note suggesting a fresh ticket when the closing is old — the
        gateway cannot cleanly redirect the message to a new thread, see
        NOTES.md)."""
        update_vals = dict(update_vals or {})
        stage_in_progress = self.env.ref(
            'liber_support.stage_in_progress', raise_if_not_found=False)
        for ticket in self:
            stage = ticket.stage_id
            if not (stage.pause_sla or stage.is_closed):
                continue
            if stage_in_progress:
                update_vals['stage_id'] = stage_in_progress.id
            if stage.is_closed and ticket.closed_date:
                age = fields.Datetime.now() - ticket.closed_date
                if age > datetime.timedelta(days=REOPEN_DAYS):
                    ticket.message_post(
                        body=_('Reopened %(days)s days after closing — '
                               'consider opening a new ticket instead.',
                               days=age.days),
                        message_type='comment',
                        subtype_xmlid='mail.mt_note')
        return super().message_update(msg_dict, update_vals=update_vals)

    def message_post(self, **kwargs):
        """First outgoing customer-visible comment stops the response
        clock. Incoming customer email also lands here, but its author has
        no internal user, so it never counts as a response.

        Customer-visible replies go out with the CLEAN layout: a support
        reply must look like a person's email, not a system notification —
        which is also what keeps it out of Gmail's Updates tab."""
        if (kwargs.get('message_type', 'notification') == 'comment'
                and kwargs.get('subtype_xmlid', 'mail.mt_comment')
                == 'mail.mt_comment'
                and 'email_layout_xmlid' not in kwargs):
            kwargs['email_layout_xmlid'] = 'liber_support.mail_layout_clean'
        message = super().message_post(**kwargs)
        mt_comment = self.env.ref('mail.mt_comment',
                                  raise_if_not_found=False)
        if (not self.sla_response_done
                and message.message_type == 'comment'
                and mt_comment and message.subtype_id == mt_comment
                and message.author_id.user_ids.filtered(
                    lambda u: not u.share)):
            self.sudo().write({'sla_response_done': fields.Datetime.now()})
            self.sudo()._update_sla_state()
        return message

    # ------------------------------------------------------------------
    # UI actions
    # ------------------------------------------------------------------

    def action_assign_to_me(self):
        self.write({'user_id': self.env.uid})
        in_progress = self.env.ref('liber_support.stage_in_progress',
                                   raise_if_not_found=False)
        for ticket in self.filtered(
                lambda t: not t.stage_id.is_closed
                and not t.stage_id.pause_sla and in_progress):
            ticket.stage_id = in_progress

    def action_open_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
        }

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    @api.depends('number', 'name')
    def _compute_display_name(self):
        for ticket in self:
            ticket.display_name = f"{ticket.number} — {ticket.name}"
