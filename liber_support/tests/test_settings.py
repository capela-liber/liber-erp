# -*- coding: utf-8 -*-
"""Company SLA defaults in Settings: a NEW team is born with them, an
existing team is never rewritten by them. Plus the tag vocabulary rules
(rename is free, duplicate is not)."""
from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import SupportCase


@tagged('post_install', '-at_install')
class TestSlaSettings(SupportCase):

    def _save_settings(self, **vals):
        settings = self.env['res.config.settings'].create(vals)
        settings.execute()
        return settings

    # -- caminho feliz -------------------------------------------------

    def test_new_team_born_with_settings_defaults(self):
        """The company default saved in Settings is what a new team
        inherits, all four targets."""
        self._save_settings(
            support_sla_response_hours_normal=4.0,
            support_sla_response_hours_urgent=1.0,
            support_sla_resolution_hours_normal=16.0,
            support_sla_resolution_hours_urgent=6.0,
        )
        team = self.env['liber.support.team'].create({
            'name': 'Nova Equipe',
            'company_id': self.company.id,
            'alias_name': 'nova-equipe-test',
        })
        self.assertEqual(team.sla_response_hours_normal, 4.0)
        self.assertEqual(team.sla_response_hours_urgent, 1.0)
        self.assertEqual(team.sla_resolution_hours_normal, 16.0)
        self.assertEqual(team.sla_resolution_hours_urgent, 6.0)

    def test_fallback_without_saved_settings(self):
        """No parameter ever saved: the shipped numbers (8/2/24/8) hold.
        cls.team from common.py was created exactly in that state."""
        self.env['ir.config_parameter'].sudo().search([
            ('key', 'like', 'liber_support.sla_%')]).unlink()
        team = self.env['liber.support.team'].create({
            'name': 'Equipe Sem Padrão',
            'company_id': self.company.id,
            'alias_name': 'sem-padrao-test',
        })
        self.assertEqual(team.sla_response_hours_normal, 8.0)
        self.assertEqual(team.sla_response_hours_urgent, 2.0)
        self.assertEqual(team.sla_resolution_hours_normal, 24.0)
        self.assertEqual(team.sla_resolution_hours_urgent, 8.0)

    # -- aresta --------------------------------------------------------

    def test_existing_team_is_not_rewritten(self):
        """Changing the company default afterwards must not touch a team
        that already exists — its numbers are its own."""
        before = (self.team.sla_response_hours_normal,
                  self.team.sla_response_hours_urgent,
                  self.team.sla_resolution_hours_normal,
                  self.team.sla_resolution_hours_urgent)
        self._save_settings(
            support_sla_response_hours_normal=3.0,
            support_sla_response_hours_urgent=0.5,
            support_sla_resolution_hours_normal=12.0,
            support_sla_resolution_hours_urgent=4.0,
        )
        self.assertEqual(
            (self.team.sla_response_hours_normal,
             self.team.sla_response_hours_urgent,
             self.team.sla_resolution_hours_normal,
             self.team.sla_resolution_hours_urgent),
            before,
            "editing the default in Settings rewrote an existing team")
        # but default_get already answers with the new numbers
        defaults = self.env['liber.support.team'].default_get(
            ['sla_response_hours_normal', 'sla_resolution_hours_normal'])
        self.assertEqual(defaults['sla_response_hours_normal'], 3.0)
        self.assertEqual(defaults['sla_resolution_hours_normal'], 12.0)

    def test_broken_parameter_falls_back(self):
        """A hand-mangled ir.config_parameter (empty or garbage) must not
        crash team creation — the shipped fallback answers."""
        self.env['ir.config_parameter'].sudo().set_param(
            'liber_support.sla_response_hours_normal', 'oito')
        team = self.env['liber.support.team'].create({
            'name': 'Equipe Param Quebrado',
            'company_id': self.company.id,
            'alias_name': 'quebrado-test',
        })
        self.assertEqual(team.sla_response_hours_normal, 8.0)


@tagged('post_install', '-at_install')
class TestTagVocabulary(SupportCase):

    def test_tag_rename_is_free(self):
        """The vocabulary belongs to the user: tags are plain records,
        renamable from the Configuration screen (no seed to fight)."""
        tag = self.env['liber.support.tag'].create({'name': 'Feira'})
        tag.name = 'Feira do livro'
        self.assertEqual(tag.name, 'Feira do livro')

    @mute_logger('odoo.sql_db')
    def test_duplicate_tag_name_rejected(self):
        self.env['liber.support.tag'].create({'name': 'Duplicada'})
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env['liber.support.tag'].create({'name': 'Duplicada'})
            self.env.flush_all()
