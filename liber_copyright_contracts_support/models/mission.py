# -*- coding: utf-8 -*-
"""A mission: one message to the authors of a set of contracts, one ticket
per author. The ticket is where the conversation lives; the mission is the
dispatch and the scoreboard (sent, answered, closed)."""
import base64
import logging
import threading

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config
from odoo.tools.misc import formatLang
from odoo.tools.pdf import merge_pdf

_logger = logging.getLogger(__name__)
# Authors handled per cron run before the job re-arms itself: enough to
# make progress visible, small enough to keep the cron's slot short.
BATCH = 15

KINDS = [
    ("statement", "Royalty statement"),
    ("settlement", "Royalty settlement"),
    ("registration", "Registration update"),
    ("other", "Other"),
]


class EdlabAuthorMission(models.Model):
    _name = "edlab.author.mission"
    _description = "Author Mission"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(required=True, tracking=True)
    kind = fields.Selection(KINDS, required=True, default="statement", tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company)
    team_id = fields.Many2one(
        "liber.support.team", string="Authors mailbox (team)",
        help="The support engine's record behind the authors' mailbox; "
        "filled in when the mission is sent.")
    template_id = fields.Many2one(
        "mail.template", string="E-mail template", required=True,
        domain="[('model', '=', 'liber.support.ticket')]",
        default=lambda self: self._default_template())
    date_to = fields.Date(
        string="Statement period end", default=fields.Date.context_today,
        help="For a statement mission: the end of the period covered by the "
        "PDF attached to each author.")
    contract_ids = fields.Many2many(
        "edlab.contract", "edlab_author_mission_contract_rel",
        "mission_id", "contract_id", string="Contracts")
    partner_ids = fields.Many2many(
        "res.partner", compute="_compute_partner_ids", string="Authors",
        help="The distinct beneficiaries of the selected contracts: one "
        "ticket and one e-mail each, whatever the number of contracts.")
    partner_count = fields.Integer(compute="_compute_partner_ids")
    ticket_ids = fields.One2many(
        "liber.support.ticket", "edlab_mission_id", string="Tickets")
    missing_email_partner_ids = fields.Many2many(
        "res.partner", compute="_compute_missing_email", string="Without e-mail",
        help="Authors of the mission with no e-mail and no ticket yet. The "
        "mission skips them and logs their names; once their e-mail is "
        "filled in, sending again reaches them and nobody else.")
    missing_email_count = fields.Integer(compute="_compute_missing_email")
    ticket_count = fields.Integer(compute="_compute_counts")
    answered_count = fields.Integer(compute="_compute_counts")
    closed_count = fields.Integer(compute="_compute_counts")
    state = fields.Selection([
        ("draft", "Draft"), ("sent", "Sent"), ("done", "Done")],
        compute="_compute_counts", store=True, tracking=True)
    sent_on = fields.Datetime(readonly=True, copy=False)
    note = fields.Text(help="Why this mission, for whoever reads it in a year.")
    queue_state = fields.Selection([
        ("idle", "Idle"), ("queued", "Queued"), ("running", "Sending")],
        default="idle", readonly=True, copy=False,
        help="Sending happens in the background: the button queues the "
        "mission and a job opens the tickets one author at a time.")
    queued_on = fields.Datetime(readonly=True, copy=False)
    sender_id = fields.Many2one(
        "res.users", string="Sent by", readonly=True, copy=False,
        help="Who pressed Send: the tickets are assigned to them and the "
        "e-mails go out in their name, even though the job runs later.")
    pending_count = fields.Integer(compute="_compute_missing_email",
                                   help="Authors with e-mail still waiting for their ticket.")
    last_error = fields.Text(readonly=True, copy=False,
                             help="The last author the job could not send to, and why.")
    # Print: the statements of the authors WITH a postal address, as one PDF
    # batch posted on the mission, for the window envelopes. Authors already
    # printed on this mission are remembered, so a second print only covers
    # the ones whose address was filled in since.
    printed_partner_ids = fields.Many2many(
        "res.partner", "edlab_author_mission_printed_rel", "mission_id", "partner_id",
        string="Printed", readonly=True, copy=False)
    missing_address_partner_ids = fields.Many2many(
        "res.partner", compute="_compute_print_pending", string="Without address",
        help="Authors not printed yet whose contact has no street or city.")
    missing_address_count = fields.Integer(compute="_compute_print_pending")
    print_pending_count = fields.Integer(compute="_compute_print_pending",
                                         help="Authors with an address still to print.")
    print_queue_state = fields.Selection([
        ("idle", "Idle"), ("queued", "Queued"), ("running", "Printing")],
        default="idle", readonly=True, copy=False)
    print_count = fields.Integer(compute="_compute_print_pending", string="Printed authors")

    @api.model
    def _default_template(self):
        return self.env.ref(
            "liber_copyright_contracts_support.mail_template_mission_statement",
            raise_if_not_found=False)

    @api.onchange("kind")
    def _onchange_kind(self):
        xmlid = {
            "statement": "mail_template_mission_statement",
            "settlement": "mail_template_mission_settlement",
            "registration": "mail_template_mission_registration",
        }.get(self.kind)
        if xmlid:
            template = self.env.ref(
                "liber_copyright_contracts_support." + xmlid, raise_if_not_found=False)
            if template:
                self.template_id = template

    @api.depends("contract_ids.royalty_line_ids.partner_id")
    def _compute_partner_ids(self):
        for mission in self:
            partners = mission.contract_ids.royalty_line_ids.partner_id
            mission.partner_ids = partners
            mission.partner_count = len(partners)

    @api.depends("ticket_ids", "ticket_ids.stage_id", "ticket_ids.message_ids")
    def _compute_counts(self):
        for mission in self:
            tickets = mission.ticket_ids
            mission.ticket_count = len(tickets)
            mission.closed_count = len(tickets.filtered(lambda t: t.stage_id.is_closed))
            mission.answered_count = len(tickets.filtered("edlab_author_answered"))
            if not tickets:
                mission.state = "draft"
            elif mission.closed_count == len(tickets):
                mission.state = "done"
            else:
                mission.state = "sent"

    # No depends through partner_ids: it is a non-stored relation and the
    # ORM cannot trace a contact's change back to the missions by SQL. The
    # values are recomputed on every read of a fresh record (the form
    # reloads, the tests invalidate).
    @api.depends("contract_ids", "ticket_ids.partner_id")
    def _compute_missing_email(self):
        for mission in self:
            pending = mission.partner_ids - mission.ticket_ids.partner_id
            missing = pending.filtered(lambda p: not p.email)
            mission.missing_email_partner_ids = missing
            mission.missing_email_count = len(missing)
            mission.pending_count = len(pending - missing)

    @staticmethod
    def _has_address(partner):
        return bool(partner.street and (partner.city or partner.zip))

    def _print_pending_partners(self):
        """Authors with a postal address and not printed on this mission."""
        self.ensure_one()
        return (self.partner_ids - self.printed_partner_ids).filtered(self._has_address)

    @api.depends("contract_ids", "printed_partner_ids")
    def _compute_print_pending(self):
        for mission in self:
            pending = mission.partner_ids - mission.printed_partner_ids
            missing = pending.filtered(lambda p: not self._has_address(p))
            mission.missing_address_partner_ids = missing
            mission.missing_address_count = len(missing)
            mission.print_pending_count = len(pending - missing)
            mission.print_count = len(mission.printed_partner_ids)

    def _contracts_of(self, partner):
        self.ensure_one()
        return self.contract_ids.filtered(
            lambda c: partner in c.royalty_line_ids.partner_id)

    def _render_message(self, ticket, statement=None):
        """Subject and body of the mission's template for this ticket, in
        the author's language, with the period, the amount and the works
        at hand for the template to quote."""
        self.ensure_one()
        partner = ticket.partner_id
        works = ticket.edlab_contract_ids.royalty_line_ids.filtered(
            lambda l: l.partner_id == partner).product_id
        ctx = {
            "edlab_works": ", ".join(works.mapped("name")),
            "edlab_contracts": ", ".join(ticket.edlab_contract_ids.mapped("name")),
            "edlab_period_label": statement["period_label"] if statement else "",
            "edlab_net_label": formatLang(
                self.env, statement["net"], currency_obj=statement["currency"])
            if statement else "",
        }
        template = self.template_id.with_context(**ctx)
        subject = template._render_field("subject", ticket.ids, compute_lang=True)[ticket.id]
        body = template._render_field("body_html", ticket.ids, compute_lang=True)[ticket.id]
        return subject, body

    def _pending_partners(self):
        """Authors with an e-mail and no ticket on this mission yet."""
        self.ensure_one()
        return (self.partner_ids - self.ticket_ids.partner_id).filtered("email")

    def action_send(self):
        """Queue the mission: the answer comes back at once, and the job
        opens one ticket per author in the background, one at a time.

        Idempotent: an author who already has a ticket on this mission is
        skipped, so queueing again only reaches the authors the first run
        did not. An author without e-mail does not stop anything: the names
        go to the chatter and the form; once the e-mail is filled in, the
        next run reaches them alone."""
        self.ensure_one()
        if not self.contract_ids:
            raise UserError(_("Choose the contracts first."))
        if not self.team_id:
            self.team_id = self.company_id._edlab_authors_team()
        already = self.ticket_ids.partner_id
        no_email = (self.partner_ids - already).filtered(lambda p: not p.email)
        if no_email:
            self.message_post(body=Markup(
                '<p class="text-warning"><strong>%s</strong> %s</p>') % (
                _("Not sent, no e-mail on file:"),
                _("%s. Fill in their e-mail and send again; only they will be reached.",
                  ", ".join(no_email.mapped("display_name")))),
                message_type="comment", subtype_xmlid="mail.mt_note")
        pending = self._pending_partners()
        if not pending:
            message = _("Every author of this mission already has a ticket.")
            if no_email:
                message += _(" %s author(s) without e-mail were skipped; see the log.",
                             len(no_email))
            return self._notify(message, success=False, sticky=bool(no_email))
        self.write({"queue_state": "queued", "queued_on": fields.Datetime.now(),
                    "sender_id": self.env.user.id, "last_error": False})
        self.message_post(body=_(
            "Queued: %s author(s) will get their ticket and e-mail in the "
            "background.", len(pending)), message_type="comment",
            subtype_xmlid="mail.mt_note")
        cron = self.env.ref("liber_copyright_contracts_support.cron_author_mission_queue",
                            raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        message = _("Sending in the background to %s author(s). Reload to "
                    "follow the ticket count.", len(pending))
        if no_email:
            message += _(" %s author(s) without e-mail were skipped; see the log.",
                         len(no_email))
        return self._notify(message, success=not no_email, sticky=bool(no_email))

    def _notify(self, message, success=True, sticky=False):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": self.name, "message": message,
                       "type": "success" if success else "warning",
                       "sticky": sticky,
                       "next": {"type": "ir.actions.client", "tag": "soft_reload"}},
        }

    def _send_to(self, partner):
        """One author: ticket, PDF when it is a statement, e-mail from the
        ticket, and the statement side effects. Returns the ticket."""
        self.ensure_one()
        contracts = self._contracts_of(partner)
        sender = self.sender_id or self.env.user
        Ticket = self.env["liber.support.ticket"].sudo()
        ticket = Ticket.create({
            "name": self.name,
            "team_id": self.team_id.id,
            "company_id": self.team_id.company_id.id,
            "partner_id": partner.id,
            "email_from": partner.email,
            "kind": "royalties",
            "channel": "manual",
            "user_id": sender.id,
            "edlab_mission_id": self.id,
            "edlab_contract_ids": [(6, 0, contracts.ids)],
        })
        statement = attachment = None
        if self.kind == "statement":
            statement, attachment = partner._edlab_statement_attachment(self.date_to)
            attachment.sudo().write({"res_model": "liber.support.ticket", "res_id": ticket.id})
        subject, body = self._render_message(ticket, statement)
        # In the sender's name: the job runs as the system, the author must
        # see a person.
        ticket.with_user(sender).message_post(
            subject=subject, body=body,
            partner_ids=partner.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            attachment_ids=attachment.ids if attachment else [])
        waiting = self.env.ref("liber_support.stage_waiting_customer",
                               raise_if_not_found=False)
        if waiting:
            ticket.stage_id = waiting
        if statement:
            partner.sudo().edlab_last_statement_date = self.date_to
            for contract in contracts:
                contract.message_post(body=_(
                    "Royalty statement (%(period)s) sent to %(author)s "
                    "on mission %(mission)s.",
                    period=statement["period_label"],
                    author=partner.display_name, mission=self.name))
        return ticket

    def _commit(self):
        """Durable progress: one author, one transaction. Not inside the
        test runner, whose cursor must stay a single rollback."""
        if not (config["test_enable"] or getattr(threading.current_thread(), "testing", False)):
            self.env.cr.commit()

    def _process_queue(self, limit=BATCH):
        """Send to up to ``limit`` pending authors of this mission, one
        transaction each. Returns the number of authors still pending."""
        self.ensure_one()
        self.queue_state = "running"
        self._commit()
        sent = 0
        for partner in self._pending_partners()[:limit]:
            try:
                with self.env.cr.savepoint():
                    self._send_to(partner)
                sent += 1
                if not self.sent_on:
                    self.sent_on = fields.Datetime.now()
            except Exception as exc:  # noqa: BLE001 -- one author must not sink the rest
                # The savepoint undid the ticket in the database; the cache
                # must forget it too, or the author would look served.
                self.env.invalidate_all()
                _logger.exception("Mission %s: could not send to %s", self.name, partner.name)
                self.last_error = "%s: %s" % (partner.display_name, exc)
                self.message_post(body=_(
                    "Could not send to %(author)s: %(error)s",
                    author=partner.display_name, error=exc),
                    message_type="comment", subtype_xmlid="mail.mt_note")
                # Park the author: a ticket without the e-mail would hide the
                # failure, so leave them pending and move on.
            self._commit()
        self.invalidate_recordset(["ticket_ids", "partner_ids"])
        remaining = len(self._pending_partners())
        failed = self.last_error and remaining
        if remaining and not failed:
            self.queue_state = "queued"
        else:
            self.queue_state = "idle"
            self.message_post(body=_(
                "Sending finished: %(tickets)s ticket(s) on this mission, "
                "%(left)s author(s) left pending.",
                tickets=len(self.ticket_ids), left=remaining),
                message_type="comment", subtype_xmlid="mail.mt_note")
        self._commit()
        return remaining

    def action_print(self):
        """Queue the print batch: the statements of every author with an
        address and not printed yet, rendered in the background into one
        PDF posted on the mission. Authors without an address are logged in
        red; once their address is filled in, the next print covers them."""
        self.ensure_one()
        if not self.contract_ids:
            raise UserError(_("Choose the contracts first."))
        if self.kind != "statement":
            raise UserError(_("Only a statement mission prints statements."))
        missing = self.missing_address_partner_ids
        if missing:
            self.message_post(body=Markup(
                '<p class="text-danger"><strong>%s</strong> %s</p>') % (
                _("Not printed, no postal address:"),
                _("%s. Fill in street and city on the contact and print again; "
                  "only they will be printed.", ", ".join(missing.mapped("display_name")))),
                message_type="comment", subtype_xmlid="mail.mt_note")
        pending = self._print_pending_partners()
        if not pending:
            message = _("Every author with an address is already printed on this mission.")
            if missing:
                message += _(" %s author(s) without address were skipped; see the log.",
                             len(missing))
            return self._notify(message, success=False, sticky=bool(missing))
        self.print_queue_state = "queued"
        cron = self.env.ref("liber_copyright_contracts_support.cron_author_mission_queue",
                            raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()
        message = _("Printing %s statement(s) in the background: the PDF batch "
                    "will be posted on this mission's log.", len(pending))
        if missing:
            message += _(" %s author(s) without address were skipped; see the log.",
                         len(missing))
        return self._notify(message, success=not missing, sticky=bool(missing))

    def _process_print(self):
        """Render each pending author's statement (envelope version), merge
        the lot into one PDF on the mission's log, remember who was printed."""
        self.ensure_one()
        self.print_queue_state = "running"
        self._commit()
        pdfs, printed, failed = [], self.env["res.partner"], []
        for partner in self._print_pending_partners():
            try:
                _statement, pdf = partner._edlab_statement_pdf(self.date_to, for_email=False)
                pdfs.append(pdf)
                printed |= partner
            except Exception as exc:  # noqa: BLE001
                _logger.exception("Mission %s: could not print %s", self.name, partner.name)
                failed.append("%s: %s" % (partner.display_name, exc))
        if pdfs:
            batch = len(self.message_ids.filtered(lambda m: m.attachment_ids)) + 1
            attachment = self.env["ir.attachment"].sudo().create({
                "name": _("Print batch %(n)s - %(mission)s.pdf", n=batch, mission=self.name),
                "type": "binary",
                "datas": base64.b64encode(merge_pdf(pdfs) if len(pdfs) > 1 else pdfs[0]),
                "res_model": self._name, "res_id": self.id,
                "mimetype": "application/pdf",
            })
            self.printed_partner_ids = [(4, p.id) for p in printed]
            self.message_post(
                body=_("Print batch %(n)s: %(count)s statement(s) for the envelopes "
                       "(%(names)s).", n=batch, count=len(printed),
                       names=", ".join(printed.mapped("display_name"))),
                attachment_ids=attachment.ids,
                message_type="comment", subtype_xmlid="mail.mt_note")
        if failed:
            self.last_error = "\n".join(failed)
            self.message_post(body=_("Could not print: %s", "; ".join(failed)),
                              message_type="comment", subtype_xmlid="mail.mt_note")
        self.print_queue_state = "idle"
        self._commit()
        return len(printed)

    @api.model
    def _cron_send_queue(self):
        """The job: one batch per queued mission, then re-arm while work
        remains. An author that failed stays pending with the error on the
        mission; the next 'send' click retries them."""
        for mission in self.search([("print_queue_state", "=", "queued")]):
            try:
                mission._process_print()
            except Exception as exc:  # noqa: BLE001
                _logger.exception("Mission %s: print failed", mission.name)
                mission.write({"print_queue_state": "idle", "last_error": str(exc)})
                mission._commit()
        missions = self.search([("queue_state", "=", "queued")], order="queued_on")
        more = False
        for mission in missions:
            try:
                remaining = mission._process_queue()
            except Exception as exc:  # noqa: BLE001
                _logger.exception("Mission %s: queue failed", mission.name)
                mission.write({"queue_state": "idle", "last_error": str(exc)})
                mission._commit()
                continue
            more = more or (remaining and mission.queue_state == "queued")
        if more:
            cron = self.env.ref("liber_copyright_contracts_support.cron_author_mission_queue",
                                raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()

    def action_view_tickets(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("liber_copyright_contracts_support.action_author_ticket")
        action["domain"] = [("edlab_mission_id", "=", self.id)]
        action["context"] = {"default_edlab_mission_id": self.id,
                             "default_team_id": self.team_id.id, "default_kind": "royalties"}
        return action

    def action_view_authors(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Authors"),
            "res_model": "res.partner", "view_mode": "list,form",
            "domain": [("id", "in", self.partner_ids.ids)],
            "context": {"create": False},
        }
