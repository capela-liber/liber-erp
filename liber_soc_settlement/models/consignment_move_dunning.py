# -*- coding: utf-8 -*-
"""Return dunning (CR chasing).

Once an operation (CO) is confirmed and the customer has the first map, the
return (CR = consignment.move of kind 'return') becomes the object the returns
team chases -- the "puxadas". This layer puts a clock on that CR and walks an
escalation ladder driven by a nightly cron, reusing the pieces already in place
(mail.activity, the 'Consignação — Respostas' channel, the escalation manager
in Settings). It never creates a CR: that is still action_run's job.

The ladder is one master window (return_sla_days) with three checkpoints given
as a percentage of it -- set the days, the calendar reflows:

    0%    CR created (clock starts, return_due_date = today + window)
    nudge%    re-send the return request + schedule a call for the responsible
    call%     the call activity comes due (human step, not the cron's)
    broadcast%    red alert in the shared channel (the whole team sees it)
    100%      escalate to the return manager; the CR is overdue
"""
from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models, _


class ConsignmentMove(models.Model):
    _inherit = 'consignment.move'

    # Who chases this return. Brought from the originating consignment operation
    # (CO), but editable -- the returns team ("puxadas") may reassign it.
    user_id = fields.Many2one(
        'res.users', string='Responsible', tracking=True,
        compute='_compute_user_id', store=True, readonly=False,
        help="Person responsible for chasing this return. Defaults to the "
             "responsible of the consignment operation (CO) that generated it.")

    @api.depends('consignment_operation_id.user_id')
    def _compute_user_id(self):
        # Only pull a value in -- never blank a manual assignment because the CO
        # has none.
        for mv in self:
            if mv.consignment_operation_id.user_id:
                mv.user_id = mv.consignment_operation_id.user_id

    # Clock lives on the CR. Set at creation for returns; the checkpoints are
    # derived from it and the Settings percentages, so nothing else is stored.
    return_due_date = fields.Date(
        string='Return Due', copy=False, tracking=True,
        help="Deadline for the customer to send the merchandise back. Set when "
             "the return (CR) is created; overdue past this date.")
    dunning_step = fields.Integer(
        string='Dunning Step', default=0, copy=False,
        help="How far up the chasing ladder this return has climbed: "
             "0 none · 1 nudged · 2 broadcast to the team · 3 escalated to the "
             "manager. Guards each rung so it fires only once.")
    dunning_stage = fields.Selection([
        ('0', 'Not chasing'),
        ('1', 'Reminder sent'),
        ('2', 'Team alerted'),
        ('3', 'Escalated'),
    ], string='Dunning Stage', compute='_compute_dunning_stage', store=True,
        help="The dunning rung as a coloured badge (blue reminder · orange team "
             "alert · red escalated).")

    @api.depends('dunning_step', 'move_kind')
    def _compute_dunning_stage(self):
        for mv in self:
            mv.dunning_stage = str(min(mv.dunning_step, 3)) if mv.move_kind == 'return' else False
    return_overdue = fields.Boolean(
        string='Overdue', compute='_compute_return_overdue', search='_search_return_overdue',
        help="A return whose due date has passed and which hasn't been "
             "returned or cancelled yet.")

    @api.depends('move_kind', 'state', 'return_due_date')
    def _compute_return_overdue(self):
        today = fields.Date.context_today(self)
        for mv in self:
            mv.return_overdue = (
                mv.move_kind == 'return' and mv.state not in ('done', 'cancel')
                and bool(mv.return_due_date) and mv.return_due_date < today)

    def _search_return_overdue(self, operator, value):
        """Make the computed flag filterable (one-click 'Overdue' filter).

        Odoo normalises `('return_overdue', '=', True)` to operator 'in' with a
        set value, so handle both the '='/'!=' and 'in'/'not in' spellings."""
        today = fields.Date.context_today(self)
        base = ['&', '&',
                ('move_kind', '=', 'return'),
                ('state', 'not in', ('done', 'cancel')),
                ('return_due_date', '<', today)]
        if operator in ('in', 'not in'):
            truthy, negate = (True in value), (operator == 'not in')
        else:  # '=', '!='
            truthy, negate = bool(value), (operator == '!=')
        want_overdue = truthy != negate
        return base if want_overdue else ['!'] + base

    # ------------------------------------------------------------------
    # Clock start: a return (CR) is born with its window already ticking.
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for mv in moves:
            if mv.move_kind == 'return' and not mv.return_due_date:
                mv.return_due_date = fields.Date.context_today(mv) + relativedelta(
                    days=mv._return_sla_days())
        return moves

    def action_release(self):
        """Carry the agreed return date (return_due_date) onto the warehouse
        transfer (RET) as its scheduled date, so logistics sees the deadline."""
        res = super().action_release()
        for mv in self:
            if mv.move_kind == 'return' and mv.return_due_date and mv.picking_id:
                mv.picking_id.scheduled_date = fields.Datetime.to_datetime(
                    mv.return_due_date)
        return res

    # ------------------------------------------------------------------
    # Settings readers
    # ------------------------------------------------------------------
    def _return_sla_days(self):
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'soc_settlement.return_sla_days', 30)) or 30

    def _dunning_pct(self, key, default):
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'soc_settlement.return_%s_pct' % key, default))

    def _checkpoint_date(self, pct):
        """Date at `pct`% of the window, counted from its start (due - window)."""
        self.ensure_one()
        sla = self._return_sla_days()
        start = self.return_due_date - relativedelta(days=sla)
        return start + relativedelta(days=round(sla * pct / 100.0))

    # ------------------------------------------------------------------
    # A return is "pending" until the goods are physically back (or it is
    # cancelled). No picking yet counts as pending -- the customer hasn't
    # sent anything.
    # ------------------------------------------------------------------
    def _return_pending(self):
        self.ensure_one()
        if self.move_kind != 'return' or self.state == 'cancel':
            return False
        return not (self.picking_id and self.picking_id.state == 'done')

    def _dunning_responsible(self):
        self.ensure_one()
        return self.user_id or self.consignment_operation_id.user_id or self.create_uid

    # ------------------------------------------------------------------
    # The engine
    # ------------------------------------------------------------------
    @api.model
    def _cron_return_dunning(self):
        """Walk every open return one rung further up the ladder if it is due.
        Idempotent: each rung is gated by dunning_step, so re-running the cron
        (or catching up after a missed day) never double-fires a step."""
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            'soc_settlement.return_dunning_enabled', 'True')
        if enabled not in ('True', 'true', '1'):
            return
        today = fields.Date.context_today(self)
        returns = self.search([
            ('move_kind', '=', 'return'),
            ('state', '!=', 'cancel'),
            ('return_due_date', '!=', False),
            ('dunning_step', '<', 3),
        ])
        for mv in returns:
            if not mv._return_pending():
                continue
            mv._run_dunning(today)

    def _run_dunning(self, today):
        self.ensure_one()
        if self.dunning_step < 1 and today >= self._checkpoint_date(
                self._dunning_pct('nudge', 25)):
            self._dunning_nudge()
            self.dunning_step = 1
        if self.dunning_step < 2 and today >= self._checkpoint_date(
                self._dunning_pct('broadcast', 65)):
            self._dunning_broadcast()
            self.dunning_step = 2
        if self.dunning_step < 3 and today >= self.return_due_date:
            self._dunning_escalate()
            self.dunning_step = 3

    # -- rung 1: re-send the request + schedule the call ----------------
    def _dunning_nudge(self):
        self.ensure_one()
        self.action_send_return_request()
        call_date = self._checkpoint_date(self._dunning_pct('call', 40))
        responsible = self._dunning_responsible()
        if responsible:
            self.activity_schedule(
                'mail.mail_activity_data_call',
                date_deadline=call_date,
                user_id=responsible.id,
                summary=_("Call the customer about the pending return %s") % self.name,
            )
        self._post_return_channel_alert(_(
            "⏳ %(customer)s hasn't returned yet — return request re-sent for "
            "%(cr)s (due %(due)s).") % {
                'customer': self.partner_id.display_name,
                'cr': self.name,
                'due': self.return_due_date,
            })

    # -- rung 2: broadcast to the whole team ----------------------------
    def _dunning_broadcast(self):
        self.ensure_one()
        self._post_return_channel_alert(_(
            "📣 Return %(cr)s from %(customer)s is closing on its deadline "
            "(%(due)s) with no return. Someone please chase it.") % {
                'cr': self.name,
                'customer': self.partner_id.display_name,
                'due': self.return_due_date,
            })

    # -- rung 3: escalate to the manager --------------------------------
    def _dunning_escalate(self):
        self.ensure_one()
        manager = self.company_id.return_escalation_manager_id
        self._post_return_channel_alert(_(
            "🚨 Return %(cr)s from %(customer)s is OVERDUE (was due %(due)s). "
            "Escalated to %(manager)s.") % {
                'cr': self.name,
                'customer': self.partner_id.display_name,
                'due': self.return_due_date,
                'manager': manager.name or _("(no manager set)"),
            })
        if manager:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=fields.Date.context_today(self),
                user_id=manager.id,
                summary=_("Overdue consignment return %s — take over") % self.name,
            )

    # ------------------------------------------------------------------
    # Outbound: the return-request e-mail and the red channel alert.
    # ------------------------------------------------------------------
    def action_send_return_request(self):
        """E-mail the customer the return request (CR), directly (no composer).
        Called by the nudge and available as a manual button on the CR."""
        template = self.env.ref(
            'liber_soc_settlement.mail_template_return_request', raise_if_not_found=False)
        for mv in self:
            if template and mv.partner_id.email:
                template.send_mail(mv.id, force_send=False)
        return True

    def _returns_channel(self):
        return self.env.ref(
            'liber_soc_settlement.channel_consignment_returns', raise_if_not_found=False)

    def message_post(self, **kwargs):
        """Everything that touches a CR lands in the Devoluções feed.

        Not only the customer's replies (the CO does that): the team's internal
        notes too. A return is a clock running against someone who is holding
        goods that are ours, and when it goes wrong what you need is the WHOLE
        conversation in one place -- including "ligamos, prometeram sexta". Half a
        thread is worse than none: it reads as if nothing happened.
        """
        message = super().message_post(**kwargs)
        channel = self._returns_channel()
        if (len(self) == 1 and channel and self.move_kind == 'return'
                and message.message_type in ('comment', 'email')
                and message.author_id != self.env.ref('base.partner_root')):
            author = message.author_id
            from_customer = author and author == self.partner_id
            colour = ('#0d6efd' if from_customer else '#6c757d')
            label = (_('replied') if from_customer else _('noted'))
            body = Markup(
                '<div style="border-left:3px solid %(colour)s;padding-left:8px;">'
                '<b>%(who)s</b> %(label)s on %(link)s<br/>%(text)s</div>'
            ) % {
                'colour': colour,
                'who': Markup.escape(author.display_name or _('Someone')),
                'label': Markup.escape(label),
                'link': self._get_html_link(),
                'text': message.body or '',
            }
            channel.message_post(
                body=body, message_type='comment', subtype_xmlid='mail.mt_comment')
        return message

    def _post_return_channel_alert(self, text):
        """Drop a red-background alert in the Devoluções feed: the dunning events
        land in the same place as the conversation they are about."""
        self.ensure_one()
        channel = self._returns_channel()
        if not channel:
            return
        # Red banner. escape() keeps the interpolated names/refs safe inside the
        # Markup body (message_post would otherwise escape the whole string).
        body = Markup(
            '<div style="background-color:#f8d7da;color:#842029;'
            'border:1px solid #f5c2c7;border-radius:4px;padding:8px;">'
            '%(link)s — %(text)s</div>'
        ) % {
            'link': self._get_html_link(),
            'text': Markup.escape(text),
        }
        channel.message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_comment')
