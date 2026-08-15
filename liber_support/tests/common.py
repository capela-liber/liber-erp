# -*- coding: utf-8 -*-
from odoo.tests import common


class SupportCase(common.TransactionCase):
    """Shared scenery. Companies are REUSED, not created —
    res.company.create breaks under account's fiscalyear constraints
    (house lesson, 2026-08)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # A deterministic 8-17 Mon-Fri calendar in UTC, so the SLA
        # arithmetic in the tests does not depend on the server timezone.
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Support Test 8-17 UTC',
            'tz': 'UTC',
            'company_id': cls.company.id,
        })
        cls.stage_new = cls.env.ref('liber_support.stage_new')
        cls.stage_in_progress = cls.env.ref(
            'liber_support.stage_in_progress')
        cls.stage_waiting_customer = cls.env.ref(
            'liber_support.stage_waiting_customer')
        cls.stage_resolved = cls.env.ref('liber_support.stage_resolved')
        cls.stage_closed = cls.env.ref('liber_support.stage_closed')

        cls.team = cls.env['liber.support.team'].create({
            'name': 'Comercial Test',
            'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar.id,
            'alias_name': 'comercial-test',
        })
        cls.Ticket = cls.env['liber.support.ticket']
