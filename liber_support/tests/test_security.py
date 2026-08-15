# -*- coding: utf-8 -*-
"""Who sees what: a user sees the tickets of their teams; the manager
sees all; whoever is outside the groups sees nothing."""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import SupportCase


@tagged('post_install', '-at_install')
class TestSecurity(SupportCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('liber_support.group_support_user')
        group_manager = cls.env.ref(
            'liber_support.group_support_manager')
        base_user = cls.env.ref('base.group_user')

        def make_user(login, groups):
            return cls.env['res.users'].with_context(
                no_reset_password=True).create({
                    'name': login, 'login': login,
                    'email': f'{login}@test.liber',
                    'group_ids': [Command.set([g.id for g in groups])],
                })

        cls.user_a = make_user('support_a', [base_user, group_user])
        cls.user_b = make_user('support_b', [base_user, group_user])
        cls.outsider = make_user('outsider', [base_user])
        cls.manager = make_user('support_mgr',
                                [base_user, group_manager])

        cls.team.member_ids = [Command.set([cls.user_a.id])]
        cls.team_b = cls.env['liber.support.team'].create({
            'name': 'Outra Equipe',
            'company_id': cls.company.id,
            'alias_name': 'outra-test',
            'member_ids': [Command.set([cls.user_b.id])],
        })
        cls.ticket_a = cls.Ticket.create(
            {'name': 'Da equipe A', 'team_id': cls.team.id})

    def test_member_reads_and_writes_own_team(self):
        ticket = self.ticket_a.with_user(self.user_a)
        self.assertEqual(ticket.name, 'Da equipe A')
        ticket.write({'priority': '1'})
        self.assertEqual(ticket.priority, '1')

    def test_member_of_other_team_sees_nothing(self):
        with self.assertRaises(AccessError):
            self.ticket_a.with_user(self.user_b).read(['name'])

    def test_unrouted_ticket_is_everyones(self):
        """No team yet = triage work: any support user must see it,
        otherwise nobody picks it up."""
        orphan = self.Ticket.create({'name': 'Sem equipe'})
        self.assertEqual(
            orphan.with_user(self.user_b).name, 'Sem equipe')

    def test_manager_sees_all(self):
        self.assertEqual(
            self.ticket_a.with_user(self.manager).name, 'Da equipe A')

    def test_outsider_is_blocked_by_acl(self):
        with self.assertRaises(AccessError):
            self.Ticket.with_user(self.outsider).search([])

    def test_user_cannot_configure_stages(self):
        with self.assertRaises(AccessError):
            self.env['liber.support.stage'].with_user(
                self.user_a).create({'name': 'Nova'})
