# -*- coding: utf-8 -*-
"""The two clocks, in working hours. The calendar is 8-12/13-17 Mon-Fri
in UTC, planted in common.py, so every expectation here is arithmetic,
not luck."""
from datetime import datetime, timedelta

from odoo import fields
from odoo.tests import tagged

from .common import SupportCase

# Friday, 2026-08-07 is a real Friday.
FRIDAY_16H = datetime(2026, 8, 7, 16, 0, 0)
FRIDAY_18H = datetime(2026, 8, 7, 18, 0, 0)
MONDAY = datetime(2026, 8, 10)


@tagged('post_install', '-at_install')
class TestSla(SupportCase):

    def _ticket(self, create_date=None, **vals):
        vals.setdefault('name', 'SLA test')
        vals.setdefault('team_id', self.team.id)
        ticket = self.Ticket.create(vals)
        if create_date:
            # create_date is ORM-magic; force it and replant the clocks.
            self.env.cr.execute(
                "UPDATE liber_support_ticket SET create_date = %s "
                "WHERE id = %s", (create_date, ticket.id))
            ticket.invalidate_recordset(['create_date'])
            ticket._sla_start()
        return ticket

    # -- plantio -------------------------------------------------------

    def test_deadline_inside_working_hours(self):
        """8 working hours from Friday 16:00 land on Monday 16:00 —
        1h left on Friday, 7h across Monday's 8-12 / 13-17 blocks."""
        ticket = self._ticket(create_date=FRIDAY_16H)
        self.assertEqual(ticket.sla_response_deadline,
                         datetime(2026, 8, 10, 16, 0, 0))

    def test_friday_evening_email_is_not_late_saturday(self):
        """The Friday 6 PM case from the spec: the clock only starts
        Monday morning; nothing may fall on the weekend."""
        ticket = self._ticket(create_date=FRIDAY_18H)
        self.assertGreaterEqual(ticket.sla_response_deadline, MONDAY)
        self.assertNotIn(ticket.sla_response_deadline.weekday(), (5, 6))
        self.assertEqual(ticket.sla_response_deadline,
                         datetime(2026, 8, 10, 17, 0, 0))

    def test_urgent_shortens_the_clock(self):
        normal = self._ticket(create_date=FRIDAY_16H)
        urgent = self._ticket(create_date=FRIDAY_16H, priority='1')
        self.assertLess(urgent.sla_response_deadline,
                        normal.sla_response_deadline)

    # -- pausa ---------------------------------------------------------

    def test_waiting_customer_pauses_resolution(self):
        ticket = self._ticket()
        deadline_before = ticket.sla_resolution_deadline
        ticket.stage_id = self.stage_waiting_customer
        self.assertTrue(ticket.sla_paused_since)
        self.assertGreater(ticket.sla_resolution_remaining_hours, 0)
        # ball comes back: clock replanted from now, not from creation
        ticket.stage_id = self.stage_in_progress
        self.assertFalse(ticket.sla_paused_since)
        self.assertEqual(ticket.sla_resolution_remaining_hours, 0)
        self.assertGreaterEqual(ticket.sla_resolution_deadline,
                                deadline_before)

    # -- primeira resposta ---------------------------------------------

    def test_internal_comment_stops_response_clock(self):
        """Posted as a real internal user — the test default (OdooBot)
        is archived and must not count as a response either."""
        ticket = self._ticket()
        self.assertFalse(ticket.sla_response_done)
        ticket.with_user(self.env.ref('base.user_admin')).message_post(
            body='Bom dia! Pedido gerado.',
            message_type='comment',
            subtype_xmlid='mail.mt_comment')
        self.assertTrue(ticket.sla_response_done)

    def test_internal_note_does_not_stop_it(self):
        ticket = self._ticket()
        ticket.message_post(body='nota interna, cliente não vê',
                            message_type='comment',
                            subtype_xmlid='mail.mt_note')
        self.assertFalse(ticket.sla_response_done)

    def test_incoming_customer_email_does_not_stop_it(self):
        partner = self.env['res.partner'].create(
            {'name': 'Cliente', 'email': 'cli@ext.test'})
        ticket = self._ticket()
        ticket.message_post(body='cliente insistindo',
                            message_type='email',
                            author_id=partner.id,
                            subtype_xmlid='mail.mt_comment')
        self.assertFalse(ticket.sla_response_done)

    # -- veredito ------------------------------------------------------

    def test_close_in_time_is_met(self):
        ticket = self._ticket()
        ticket.with_user(self.env.ref('base.user_admin')).message_post(
            body='resolvido!', message_type='comment',
            subtype_xmlid='mail.mt_comment')
        ticket.stage_id = self.stage_resolved
        self.assertEqual(ticket.sla_state, 'met')
        self.assertTrue(ticket.closed_date)

    def test_close_late_is_missed(self):
        ticket = self._ticket(
            create_date=fields.Datetime.now() - timedelta(days=30))
        ticket.stage_id = self.stage_closed
        self.assertEqual(ticket.sla_state, 'missed')

    def test_late_ticket_goes_late_and_cron_nags(self):
        ticket = self._ticket(
            create_date=fields.Datetime.now() - timedelta(days=30))
        self.Ticket._cron_update_sla()
        self.assertEqual(ticket.sla_state, 'late')
        self.assertTrue(ticket.activity_ids,
                        "going late must nag somebody")

    def test_ticket_without_team_has_no_clock(self):
        ticket = self.Ticket.create({'name': 'Sem equipe'})
        self.assertFalse(ticket.sla_response_deadline)
        self.assertEqual(ticket.sla_state, 'ok')

    def test_close_in_time_without_response_is_met(self):
        """Fechado dentro do prazo SEM primeira resposta registrada é
        Cumprido — o fechamento respondeu (correção de 10/08: dava
        Perdido 'meio sem lógica')."""
        ticket = self._ticket()
        ticket.stage_id = self.stage_resolved
        self.assertEqual(ticket.sla_state, 'met')

    def test_closed_ticket_never_replants_clock(self):
        """Editar prioridade de chamado fechado (histórico importado) não
        pode ressuscitar prazo."""
        ticket = self._ticket()
        ticket.stage_id = self.stage_closed
        ticket.write({'sla_response_deadline': False,
                      'sla_resolution_deadline': False})
        ticket.priority = '1'
        self.assertFalse(ticket.sla_response_deadline)
        self.assertFalse(ticket.sla_resolution_deadline)
