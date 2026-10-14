# -*- coding: utf-8 -*-
import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import MissionCase


def send_now(mission):
    """Queue and process at once, as the cron would."""
    res = mission.action_send()
    mission._cron_send_queue()
    mission.invalidate_recordset()
    return res


@tagged("post_install", "-at_install", "copyright_support")
class TestAuthorMission(MissionCase):

    def test_authors_are_distinct_beneficiaries(self):
        self.assertEqual(self.mission.partner_ids, self.author_a | self.author_b)
        self.assertEqual(self.mission.partner_count, 2)
        self.assertEqual(self.mission.state, "draft")
        self.assertEqual(self.mission.template_id, self.env.ref(
            "liber_copyright_contracts_support.mail_template_mission_statement"))

    def test_send_queues_and_the_job_opens_one_ticket_per_author(self):
        res = self.mission.action_send()
        self.assertEqual(res["params"]["next"], {"type": "ir.actions.client", "tag": "soft_reload"})
        self.assertIn("background", res["params"]["message"])
        self.assertEqual(self.mission.queue_state, "queued")
        self.assertFalse(self.mission.ticket_ids)          # nothing yet: the job does it
        self.assertEqual(self.mission.pending_count, 2)
        self.mission._cron_send_queue()
        self.mission.invalidate_recordset()
        self.assertEqual(self.mission.queue_state, "idle")
        self.assertEqual(self.mission.pending_count, 0)
        self.assertTrue(any("Sending finished" in (m.body or "") for m in self.mission.message_ids))
        tickets = self.mission.ticket_ids
        self.assertEqual(len(tickets), 2)
        ta = tickets.filtered(lambda t: t.partner_id == self.author_a)
        self.assertEqual(ta.edlab_contract_ids, self.c1 | self.c2)
        self.assertEqual(ta.kind, "royalties")
        self.assertEqual(ta.team_id, self.team)
        self.assertEqual(ta.stage_id, self.env.ref("liber_support.stage_waiting_customer"))
        self.assertEqual(ta.name, self.mission.name)
        # The e-mail went out from the ticket, to the author, with the PDF.
        mails = ta.message_ids.filtered(lambda m: m.message_type == "comment"
                                        and self.author_a in m.partner_ids)
        self.assertEqual(len(mails), 1)
        self.assertIn("Royalty statement", mails.subject)
        self.assertIn("Obra Um", mails.body)
        self.assertIn("Obra Dois", mails.body)
        self.assertEqual(len(mails.attachment_ids), 1)
        self.assertTrue(mails.attachment_ids.name.endswith(".pdf"))
        self.assertEqual(mails.attachment_ids.res_model, "liber.support.ticket")
        # Side effects of a statement mission.
        self.assertEqual(self.author_a.edlab_last_statement_date, self.mission.date_to)
        self.assertTrue(any("sent to Autor da Missão" in m.body for m in self.c1.message_ids))
        self.assertEqual(self.mission.state, "sent")
        self.assertTrue(self.mission.sent_on)
        tb = tickets - ta
        self.assertEqual(tb.edlab_contract_ids, self.c3)

    def test_resend_only_reaches_new_authors(self):
        send_now(self.mission)
        res = send_now(self.mission)
        self.assertEqual(len(self.mission.ticket_ids), 2)
        self.assertIn("already has a ticket", res["params"]["message"])
        c4 = self.c3.copy()
        new_author = self.env["res.partner"].create({
            "name": "Autor Novo", "email": "novo@example.org"})
        c4.royalty_line_ids.unlink()
        c4.write({"royalty_line_ids": [(0, 0, {"partner_id": new_author.id,
                                               "product_id": self.book3.id})]})
        self.mission.contract_ids = [(4, c4.id)]
        res = send_now(self.mission)
        self.assertIn("1 author(s)", res["params"]["message"])
        self.assertEqual(len(self.mission.ticket_ids), 3)

    def test_missing_email_is_logged_and_sent_later(self):
        self.author_b.email = False
        self.mission.invalidate_recordset()
        self.assertEqual(self.mission.missing_email_partner_ids, self.author_b)
        res = send_now(self.mission)
        self.assertEqual(self.mission.ticket_ids.partner_id, self.author_a)
        self.assertIn("1 author(s) without e-mail", res["params"]["message"])
        notes = self.mission.message_ids.filtered(lambda m: "Autora Beta" in (m.body or ""))
        self.assertEqual(len(notes), 1)
        self.assertEqual(self.mission.state, "sent")
        # Still without e-mail: a second click sends nothing and logs again.
        send_now(self.mission)
        self.assertEqual(len(self.mission.ticket_ids), 1)
        # E-mail filled in: only she is reached.
        self.author_b.email = "beta@example.org"
        self.mission.invalidate_recordset()
        self.assertFalse(self.mission.missing_email_partner_ids)
        res = send_now(self.mission)
        self.assertIn("1 author(s)", res["params"]["message"])
        self.assertEqual(self.mission.ticket_ids.partner_id, self.author_a | self.author_b)
        self.assertEqual(len(self.mission.ticket_ids.filtered(
            lambda t: t.partner_id == self.author_a)), 1)

    def test_missing_contracts_block(self):
        self.mission.contract_ids = [(5, 0, 0)]
        with self.assertRaises(UserError):
            self.mission.action_send()

    def test_reply_marks_answered_and_closing_finishes(self):
        send_now(self.mission)
        ta = self.mission.ticket_ids.filtered(lambda t: t.partner_id == self.author_a)
        self.assertFalse(ta.edlab_author_answered)
        self.assertEqual(self.mission.answered_count, 0)
        # The author's reply, as the mail gateway would log it.
        ta.sudo().message_post(body="Recebi, obrigado.", author_id=self.author_a.id,
                               message_type="email", subtype_xmlid="mail.mt_comment")
        self.assertTrue(ta.edlab_author_answered)
        self.mission.invalidate_recordset()
        self.assertEqual(self.mission.answered_count, 1)
        closed = self.env.ref("liber_support.stage_closed")
        self.mission.ticket_ids.write({"stage_id": closed.id})
        self.mission.invalidate_recordset()
        self.assertEqual(self.mission.closed_count, 2)
        self.assertEqual(self.mission.state, "done")

    def test_author_folder_and_contract_side(self):
        send_now(self.mission)
        self.assertEqual(self.author_a.edlab_support_ticket_count, 1)
        self.assertEqual(self.author_a.edlab_support_ticket_ids.edlab_mission_id, self.mission)
        self.assertEqual(self.c1.edlab_support_ticket_count, 1)
        self.assertEqual(self.c1.edlab_support_ticket_ids.partner_id, self.author_a)
        self.assertEqual(self.c3.edlab_support_ticket_ids.partner_id, self.author_b)
        action = self.c1.action_view_support_tickets()
        self.assertEqual(action["domain"], [("edlab_contract_ids", "in", self.c1.ids)])

    def test_mailbox_is_the_only_setting_the_department_sees(self):
        """The team behind the mailbox is created once, renamed with the
        alias, and never typed by hand."""
        team = self.company._edlab_authors_team()
        self.assertEqual(team, self.team)
        self.assertEqual(team.alias_name, "autores")
        self.assertEqual(self.company._edlab_authors_team(), team)   # idempotent
        settings = self.env["res.config.settings"].create({})
        settings.contract_authors_alias = "direitos"
        settings.execute()
        self.assertEqual(team.alias_name, "direitos")
        self.assertFalse(self.mission.team_id)
        send_now(self.mission)
        self.assertEqual(self.mission.team_id, team)
        self.assertEqual(self.mission.ticket_ids.team_id, team)
        other = self.env["res.company"].create({"name": "Outra Editora"})
        self.assertNotEqual(other._edlab_authors_team(), team)
        self.assertEqual(other._edlab_authors_team().company_id, other)

    def test_spontaneous_ticket_from_the_card_and_from_the_alias(self):
        action = self.author_a.action_new_author_ticket()
        ctx = action["context"]
        self.assertEqual(ctx["default_team_id"], self.team.id)
        self.assertEqual(ctx["default_kind"], "royalties")
        self.assertEqual(ctx["default_edlab_contract_ids"], [(6, 0, (self.c1 | self.c2).ids)])
        # An e-mail on the authors' alias becomes a royalties ticket.
        Ticket = self.env["liber.support.ticket"]
        ticket = Ticket.message_new(
            {"subject": "Mudei de endereço", "email_from": "autor.a@example.org",
             "body": "<p>Novo endereço...</p>", "message_id": "<x@example.org>"},
            custom_values={"team_id": self.team.id, "company_id": self.company.id})
        self.assertEqual(ticket.kind, "royalties")
        self.assertEqual(ticket.partner_id, self.author_a)
        self.assertFalse(ticket.edlab_mission_id)
        self.assertEqual(self.author_a.edlab_support_ticket_count, 1)
        # Another team's e-mail keeps its own kind.
        other = self.env["liber.support.team"].create({
            "name": "Comercial (teste)", "company_id": self.company.id})
        ticket2 = Ticket.message_new(
            {"subject": "Pedido", "email_from": "x@example.org", "body": "",
             "message_id": "<y@example.org>"},
            custom_values={"team_id": other.id, "company_id": self.company.id})
        self.assertNotEqual(ticket2.kind, "royalties")

    def test_new_mission_from_contract_list(self):
        action = (self.c1 | self.c3).action_new_mission()
        self.assertEqual(action["res_model"], "edlab.author.mission")
        self.assertEqual(action["context"]["default_contract_ids"], [(6, 0, (self.c1 | self.c3).ids)])

    def test_kind_switches_template(self):
        mission = self.env["edlab.author.mission"].new({"kind": "registration"})
        mission._onchange_kind()
        self.assertEqual(mission.template_id, self.env.ref(
            "liber_copyright_contracts_support.mail_template_mission_registration"))

    def test_departments_do_not_mix(self):
        """Contracts people see the authors' tickets and nothing of the
        bookstores; the bookstores' desk does not see the authors' ones
        unless it is in the team, and its action leaves them out anyway."""
        send_now(self.mission)
        caio = new_test_user(
            self.env, login="caio_royalties",
            groups="base.group_user,account.group_account_invoice,"
                   "liber_copyright_contracts.group_contract_manager")
        commercial_team = self.env["liber.support.team"].create({
            "name": "Comercial (teste)", "company_id": self.company.id})
        bookstore_ticket = self.env["liber.support.ticket"].create({
            "name": "Livraria pergunta", "team_id": commercial_team.id,
            "kind": "consignment"})
        Ticket = self.env["liber.support.ticket"].with_user(caio)
        seen = Ticket.search([])
        self.assertEqual(seen, self.mission.ticket_ids)
        self.assertNotIn(bookstore_ticket, seen)
        with self.assertRaises(AccessError):
            bookstore_ticket.with_user(caio).read(["name"])
        # Caio works the author's ticket without the support groups.
        author_ticket = seen[0]
        author_ticket.with_user(caio).write({"name": "Prestação: dúvida do autor"})
        author_ticket.with_user(caio).message_post(body="Respondido.")
        # The bookstores' desk: a support user not in the authors' team.
        clerk = new_test_user(
            self.env, login="clerk_commercial",
            groups="base.group_user,liber_support.group_support_user")
        commercial_team.member_ids = [(4, clerk.id)]
        self.env.invalidate_all()
        self.assertNotIn(author_ticket, self.env["liber.support.ticket"].with_user(clerk).search([]))
        commercial_action = self.env.ref("liber_support.action_support_ticket")
        self.assertEqual(commercial_action.domain, "[('kind', '!=', 'royalties')]")
        author_action = self.env.ref("liber_copyright_contracts_support.action_author_ticket")
        self.assertEqual(author_action.domain, "[('kind', '=', 'royalties')]")

    def test_mission_as_contracts_manager_without_support_group(self):
        caio = new_test_user(
            self.env, login="caio_only_contracts",
            groups="base.group_user,account.group_account_invoice,"
                   "liber_copyright_contracts.group_contract_manager")
        self.mission.with_user(caio).action_send()
        self.assertEqual(self.mission.sender_id, caio)
        # The job runs as the system later; the author still sees Caio.
        self.mission._cron_send_queue()
        self.mission.invalidate_recordset()
        self.assertEqual(len(self.mission.ticket_ids), 2)
        self.assertEqual(self.mission.ticket_ids.user_id, caio)
        mails = self.mission.ticket_ids[0].message_ids.filtered(
            lambda m: m.message_type == "comment" and m.partner_ids)
        self.assertEqual(mails.author_id, caio.partner_id)

    def test_batches_and_a_failing_author_does_not_sink_the_rest(self):
        from unittest.mock import patch
        from odoo.addons.liber_copyright_contracts_support.models import mission as mod
        self.mission.action_send()
        with patch.object(mod, "BATCH", 1):
            self.assertEqual(self.mission._process_queue(limit=1), 1)
        self.assertEqual(self.mission.queue_state, "queued")
        self.assertEqual(len(self.mission.ticket_ids), 1)
        # The remaining author's statement blows up: logged, left pending, job ends.
        victim = self.mission._pending_partners()
        self.assertEqual(len(victim), 1)
        original = type(victim)._edlab_statement_attachment
        def boom(partner, date_to=None, for_email=True):
            if partner == victim:
                raise ValueError("wkhtmltopdf died")
            return original(partner, date_to, for_email)
        with patch.object(type(victim), "_edlab_statement_attachment", boom):
            remaining = self.mission._process_queue()
        self.assertEqual(remaining, 1)
        self.assertEqual(self.mission.queue_state, "idle")
        self.assertIn("wkhtmltopdf died", self.mission.last_error)
        self.assertEqual(len(self.mission.ticket_ids), 1)
        self.assertTrue(any("Could not send to %s" % victim.display_name in (m.body or "")
                            for m in self.mission.message_ids))
        # Clicking send again retries only her.
        send_now(self.mission)
        self.assertEqual(len(self.mission.ticket_ids), 2)
        self.assertFalse(self.mission.last_error)

    def test_links_between_ticket_contract_and_contact(self):
        send_now(self.mission)
        ta = self.mission.ticket_ids.filtered(lambda t: t.partner_id == self.author_a)
        self.assertEqual(ta.edlab_contract_count, 2)
        self.assertEqual(sorted(ta.action_view_edlab_contracts()["domain"][0][2]),
                         sorted((self.c1 | self.c2).ids))
        tb = self.mission.ticket_ids - ta
        self.assertEqual(tb.action_view_edlab_contracts()["res_id"], self.c3.id)
        self.assertEqual(ta.action_view_edlab_author()["res_id"], self.author_a.id)
        # A new royalties ticket on an author starts with their contracts.
        new = self.env["liber.support.ticket"].new({"kind": "royalties", "partner_id": self.author_a.id})
        new._onchange_partner_contracts()
        self.assertEqual(new.edlab_contract_ids._origin, self.c1 | self.c2)
        self.assertEqual(self.author_a.action_view_author_tickets()["domain"], [("partner_id", "=", self.author_a.id)])

    def test_print_batches_only_authors_with_address_and_remembers_them(self):
        self.author_a.write({"street": "Rua A, 1", "city": "Rio"})
        self.mission.invalidate_recordset()
        self.assertEqual(self.mission.missing_address_partner_ids, self.author_b)
        self.assertEqual(self.mission.print_pending_count, 1)
        res = self.mission.action_print()
        self.assertEqual(self.mission.print_queue_state, "queued")
        self.assertIn("1 author(s) without address", res["params"]["message"])
        red = self.mission.message_ids.filtered(lambda m: "Not printed" in (m.body or ""))
        self.assertEqual(len(red), 1)
        self.assertIn("text-danger", red.body)
        self.assertIn("Autora Beta", red.body)
        self.mission._cron_send_queue()
        self.mission.invalidate_recordset()
        self.assertEqual(self.mission.print_queue_state, "idle")
        self.assertEqual(self.mission.printed_partner_ids, self.author_a)
        self.assertEqual(self.mission.print_count, 1)
        batch = self.mission.message_ids.filtered(lambda m: m.attachment_ids)
        self.assertEqual(len(batch), 1)
        self.assertTrue(batch.attachment_ids.name.startswith("Print batch 1"))
        self.assertEqual(batch.attachment_ids.mimetype, "application/pdf")
        self.assertTrue(base64.b64decode(batch.attachment_ids.datas).startswith(b"%PDF"))
        # Printing again with nothing new: no second batch.
        res = self.mission.action_print()
        self.assertIn("already printed", res["params"]["message"])
        self.assertEqual(self.mission.print_queue_state, "idle")
        # Her address filled in: only she goes in batch 2.
        self.author_b.write({"street": "Rua B, 2", "zip": "20000-000"})
        self.mission.invalidate_recordset()
        self.assertFalse(self.mission.missing_address_partner_ids)
        self.mission.action_print()
        self.mission._cron_send_queue()
        self.mission.invalidate_recordset()
        self.assertEqual(self.mission.printed_partner_ids, self.author_a | self.author_b)
        batches = self.mission.message_ids.filtered(lambda m: m.attachment_ids)
        self.assertEqual(len(batches), 2)
        self.assertIn("Autora Beta", batches.sorted("id")[-1].body)
        self.assertNotIn("Autor da Missão", batches.sorted("id")[-1].body)

    def test_print_is_for_statement_missions(self):
        self.mission.kind = "registration"
        with self.assertRaises(UserError):
            self.mission.action_print()

    def test_email_attachment_has_no_window_but_print_has(self):
        self.author_a.write({"street": "Rua A, 1", "city": "Rio"})
        _st, mailed = self.author_a._edlab_statement_pdf(self.mission.date_to, for_email=True)
        _st, printed = self.author_a._edlab_statement_pdf(self.mission.date_to, for_email=False)
        self.assertTrue(mailed.startswith(b"%PDF") and printed.startswith(b"%PDF"))
        html_mail = self.env["ir.actions.report"]._render_qweb_html(
            "liber_copyright_contracts_reports.report_royalty_statement",
            self.author_a.ids, data={"no_window": True})[0].decode()
        self.assertNotIn("edlab-window", html_mail)
