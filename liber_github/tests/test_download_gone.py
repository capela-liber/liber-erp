# -*- coding: utf-8 -*-
"""The download door, as a reader, on a file the repository let go.

The screen the reader met on 30/09/2026 was "Unprocessable Entity" over
GitHub's raw JSON. The door now answers a page that says what happened,
archives the stale record and leaves the note on its chatter -- and the
archive must survive the answer (a raised error would roll it back).
"""
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.liber_cloud_files.exceptions import CloudFileGone
from odoo.addons.liber_github.services.github_api import GitHubClient

#: login and password of the test user; the password references it (see
#: CLAUDE.md: a literal would trip the secret scan of the publish).
LOGIN = 'github_reader_gone'


def _client_stub(self, account):
    pass


@tagged('post_install', '-at_install')
class TestDownloadGone(HttpCase):

    def setUp(self):
        super().setUp()
        company = self.env.company
        role = self.env['res.groups'].create({'name': 'Gone role: reads'})
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'GitHub Reader, gone file', 'login': LOGIN,
            'password': LOGIN, 'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('liber_github.group_liber_github_user').id),
                (4, role.id)],
        })
        Account = self.env['liber.cloud.account']
        if not Account.search([('provider', '=', 'github'),
                               ('company_id', '=', company.id)]):
            Account.create({'provider': 'github', 'company_id': company.id,
                            'github_token': 't'})
        folder = self.env['liber.cloud.folder'].create({
            'name': 'Arquivos do teste', 'provider': 'github',
            'path': '/HEDRA', 'external_id': 'edlab/acervo',
            'github_branch': 'main', 'read_group_ids': [(4, role.id)]})
        self.file = self.env['liber.cloud.file'].create({
            'folder_id': folder.id, 'name': 'KAAPOR_AVES_CAPA.pdf',
            'path': '/HEDRA/KAAPOR_AVES_CAPA.pdf'})

    def test_gone_file_gets_a_page_an_archive_and_a_note(self):
        gone = CloudFileGone(
            'HEDRA/KAAPOR_AVES_CAPA.pdf is no longer in edlab/acervo',
            detail='Last change on that path: "Delete HEDRA/KAAPOR_AVES_CAPA.pdf"')
        self.authenticate(LOGIN, LOGIN)
        with patch.object(GitHubClient, '__init__', _client_stub), \
             patch.object(GitHubClient, 'download', side_effect=gone):
            resp = self.url_open('/liber_cloud/download/%d' % self.file.id)
        self.assertEqual(resp.status_code, 404)
        self.assertIn('KAAPOR_AVES_CAPA.pdf', resp.text)
        self.assertIn('Delete HEDRA/KAAPOR_AVES_CAPA.pdf', resp.text)
        self.assertNotIn('Unprocessable', resp.text)
        self.assertFalse(self.file.active, "Archived, as the sync would.")
        note = self.file.message_ids[:1]
        self.assertIn('Delete HEDRA/KAAPOR_AVES_CAPA.pdf', note.body)

    def test_any_other_failure_keeps_the_record(self):
        """Only a file that left is archived: GitHub being down is not."""
        self.authenticate(LOGIN, LOGIN)
        with patch.object(GitHubClient, '__init__', _client_stub), \
             patch.object(GitHubClient, 'download',
                          side_effect=Exception('GitHub is down')), \
             self.assertLogs('odoo.http', level='ERROR'):
            resp = self.url_open('/liber_cloud/download/%d' % self.file.id)
        self.assertNotEqual(resp.status_code, 200)
        self.assertTrue(self.file.active)
