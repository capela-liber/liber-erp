# -*- coding: utf-8 -*-
"""The ticket's life: born from mail, glued to the right partner (or to
none), threaded, reopened."""
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import SupportCase

RAW_MAIL = """From: {email_from}
To: {to}
Subject: {subject}
Message-Id: {msg_id}
{extra}Content-Type: text/plain; charset=UTF-8

{body}
"""


@tagged('post_install', '-at_install')
class TestTicketGateway(SupportCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alias_domain = cls.env['mail.alias.domain'].search(
            [], limit=1) or cls.env['mail.alias.domain'].create(
            {'name': 'test.liber.press'})
        cls.company.alias_domain_id = cls.alias_domain
        cls.team.alias_id.alias_domain_id = cls.alias_domain
        cls.to_addr = (f"{cls.team.alias_name}"
                       f"@{cls.alias_domain.name}")

    def _process(self, email_from, subject, body, msg_id,
                 references=None):
        extra = f"References: {references}\n" if references else ""
        raw = RAW_MAIL.format(
            email_from=email_from, to=self.to_addr, subject=subject,
            msg_id=msg_id, body=body, extra=extra)
        return self.env['mail.thread'].message_process(False, raw)

    def _find(self, name, operator='='):
        """Tickets of THIS test's team only. The `testing` base carries
        the chamados imported from the Helpdesk 15, and subjects like
        'Envio de livros' repeat in there -- a search by name alone
        catches them and the count lies."""
        return self.Ticket.search([('name', operator, name),
                                   ('team_id', '=', self.team.id)])

    # -- caminho feliz -------------------------------------------------

    def test_email_creates_ticket_on_team(self):
        """An email to the team alias becomes a ticket of that team, in
        the team's company, numbered AT/, kind guessed from the subject."""
        self._process('Caio <direitos@hedra-test.com.br>',
                      'Envio de livros', '3 Fim do SUS?, aos cuidados de '
                      'Caroline', '<t1@ext>')
        ticket = self._find('Envio de livros')
        self.assertEqual(len(ticket), 1)
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.company_id, self.team.company_id)
        self.assertTrue(ticket.number.startswith('AT/'))
        self.assertEqual(ticket.channel, 'email')
        self.assertEqual(ticket.kind, 'shipment')
        self.assertFalse(ticket.partner_id,
                         "unknown sender must not be matched")
        self.assertIn('direitos@hedra-test.com.br', ticket.email_from)
        # SLA clocks planted on arrival
        self.assertTrue(ticket.sla_response_deadline)
        self.assertTrue(ticket.sla_resolution_deadline)

    def test_reply_threads_into_same_ticket(self):
        """A reply carrying References must update the ticket, not open a
        second one."""
        self._process('a@ext.test', 'Pedido 123', 'primeira', '<r1@ext>')
        ticket = self._find('Pedido 123')
        first_msg = ticket.message_ids[:1]
        self._process('a@ext.test', 'Re: Pedido 123', 'segunda',
                      '<r2@ext>', references=first_msg.message_id)
        tickets = self._find('Pedido 123', 'like')
        self.assertEqual(tickets, ticket,
                         "the reply must not create a new ticket")
        self.assertGreater(len(ticket.message_ids), len(first_msg))

    # -- casar o parceiro ----------------------------------------------

    def test_partner_match_unique_email(self):
        partner = self.env['res.partner'].create({
            'name': 'Livraria Única',
            'email': 'unica@livraria.test'})
        self._process('unica@livraria.test', 'Consignação nova',
                      'quero consignar', '<p1@ext>')
        ticket = self._find('Consignação nova')
        self.assertEqual(ticket.partner_id, partner)
        self.assertEqual(ticket.kind, 'consignment')

    def test_partner_no_match_on_duplicate_email(self):
        """17,044 duplicated emails in the real base: a duplicate must
        link nobody — the wrong bookstore is worse than none."""
        self.env['res.partner'].create([
            {'name': 'Livraria A', 'email': 'dupe@livraria.test'},
            {'name': 'Livraria B', 'email': 'dupe@livraria.test'},
        ])
        self._process('dupe@livraria.test', 'Acerto pendente',
                      'cadê meu acerto', '<p2@ext>')
        ticket = self._find('Acerto pendente')
        self.assertFalse(ticket.partner_id)
        self.assertEqual(ticket.email_from, 'dupe@livraria.test')

    # -- reabertura ----------------------------------------------------

    def test_reopen_recently_closed(self):
        ticket = self.Ticket.create({
            'name': 'Fechado ontem', 'team_id': self.team.id,
            'stage_id': self.stage_resolved.id})
        ticket.closed_date = fields.Datetime.now() - timedelta(days=2)
        ticket.message_update({'subject': 'Re: Fechado ontem'})
        self.assertEqual(ticket.stage_id, self.stage_in_progress)
        self.assertFalse(ticket.closed_date)

    def test_reopen_stale_posts_warning(self):
        ticket = self.Ticket.create({
            'name': 'Fechado há um mês', 'team_id': self.team.id,
            'stage_id': self.stage_closed.id})
        ticket.closed_date = fields.Datetime.now() - timedelta(days=30)
        before = len(ticket.message_ids)
        # `lang='en_US'` is not decoration: the warning is posted with `_()`,
        # so once liber_support gained a pt_BR translation this test started
        # reading "considere abrir um novo chamado" and looking for the
        # English "new ticket" in it. Asserting on prose is fine; asserting on
        # prose in whatever language the running user happens to have is a
        # test that breaks on a translation commit, far from the code it
        # guards. Pin the language and the assertion means what it says.
        ticket.with_context(lang='en_US').message_update(
            {'subject': 'Re: Fechado há um mês'})
        self.assertEqual(ticket.stage_id, self.stage_in_progress)
        notes = ticket.message_ids[:len(ticket.message_ids) - before]
        self.assertTrue(any('new ticket' in (m.body or '')
                            for m in notes),
                        "stale reopen must warn the team")


@tagged('post_install', '-at_install')
class TestKindGuess(SupportCase):
    """The keyword guess is a pure function — no records involved."""

    def test_guess_from_real_subjects(self):
        guess = self.Ticket._guess_kind
        # real subjects from the commercial mailbox, Aug/2026
        self.assertEqual(guess('Envio de livros'), 'shipment')
        self.assertEqual(guess('Envios de livros internacionais'),
                         'shipment')
        self.assertEqual(guess('Banguela, venda especial'), 'sale')
        self.assertEqual(guess('Re: Acerto de março'), 'settlement')
        self.assertEqual(guess('Nota fiscal do pedido'), 'fiscal')
        self.assertEqual(guess('Boleto vencido'), 'billing')
        self.assertEqual(guess('Atualização de cadastro'), 'registration')
        self.assertEqual(guess('Bom dia'), 'other')

    def test_subject_wins_over_body(self):
        self.assertEqual(
            self.Ticket._guess_kind('Envio de livros',
                                    'sobre o boleto anexo'),
            'shipment')

    def test_body_used_when_subject_silent(self):
        self.assertEqual(
            self.Ticket._guess_kind('Bom dia',
                                    'preciso da nota fiscal do pedido'),
            'fiscal')

    def test_empty_everything(self):
        self.assertEqual(self.Ticket._guess_kind('', ''), 'other')
        self.assertEqual(self.Ticket._guess_kind(None, None), 'other')


@tagged('post_install', '-at_install')
class TestCleanLayout(SupportCase):
    """Resposta de chamado sai sem moldura de notificação — e-mail de
    gente, fora da aba Atualizações do Gmail (11/08/2026)."""

    def test_reply_uses_clean_layout(self):
        partner = self.env['res.partner'].create(
            {'name': 'Cliente Limpo', 'email': 'limpo@cliente.test'})
        ticket = self.Ticket.create({
            'name': 'Layout', 'team_id': self.team.id,
            'partner_id': partner.id})
        msg = ticket.with_user(
            self.env.ref('base.user_admin')).with_context(
            mail_notify_force_send=False).message_post(
            body='Resposta humana.', message_type='comment',
            subtype_xmlid='mail.mt_comment', partner_ids=[partner.id])
        self.assertEqual(msg.email_layout_xmlid,
                         'liber_support.mail_layout_clean')
        mail = self.env['mail.mail'].search(
            [('mail_message_id', '=', msg.id)], limit=1)
        self.assertTrue(mail, "gerou e-mail de saída")
        self.assertIn('Resposta humana.', mail.body_html)
        self.assertNotIn('View', mail.body_html,
                         "sem botão de sistema na resposta")

    def test_internal_note_keeps_default(self):
        ticket = self.Ticket.create(
            {'name': 'Nota', 'team_id': self.team.id})
        msg = ticket.message_post(body='nota interna',
                                  message_type='comment',
                                  subtype_xmlid='mail.mt_note')
        self.assertFalse(msg.email_layout_xmlid)
