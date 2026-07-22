# -*- coding: utf-8 -*-
"""The GitHub body on the chassis: registration, the tree walk, the share."""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_github.services.github_api import GitHubClient


def _client_stub(self, account):
    pass


@tagged('post_install', '-at_install')
class TestGitHub(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['liber.cloud.account']
        cls.account = Account.search([
            ('provider', '=', 'github'),
            ('company_id', '=', cls.env.company.id)], limit=1) or \
            Account.create({
                'provider': 'github', 'company_id': cls.env.company.id,
                'github_token': 't'})
        cls.folder = cls.env['liber.cloud.folder'].create({
            'name': 'Originais', 'path': '/originais',
            'provider': 'github', 'external_id': 'edlab/acervo',
            'github_branch': 'main', 'recursive': True})

    def test_provider_registered(self):
        client = self.env['liber.cloud.provider']._client(self.account)
        self.assertIsInstance(client, GitHubClient)
        self.assertEqual(
            self.env['liber.cloud.provider']._manager_group('github'),
            'liber_github.group_liber_github_manager')
        self.assertFalse(client.supports_expiration)

    def test_folder_needs_owner_repo(self):
        naked = self.env['liber.cloud.folder'].create({
            'name': 'Solto', 'path': '/x', 'provider': 'github',
            'external_id': 'sem-barra'})
        with patch.object(GitHubClient, '__init__', _client_stub):
            client = GitHubClient(None)
            with self.assertRaises(UserError):
                client.list_folder(naked)

    def test_list_walks_the_tree(self):
        tree = {'tree': [
            {'type': 'blob', 'path': 'originais/livro-a.pdf',
             'sha': 's1', 'size': 10},
            {'type': 'blob', 'path': 'originais/antigos/livro-b.pdf',
             'sha': 's2', 'size': 20},
            {'type': 'blob', 'path': 'LEIA-ME.md', 'sha': 's3', 'size': 5},
            {'type': 'tree', 'path': 'originais/antigos', 'sha': 's4'},
        ]}
        with patch.object(GitHubClient, '__init__', _client_stub), \
             patch.object(GitHubClient, '_request', return_value=tree):
            client = GitHubClient(None)
            entries = client.list_folder(self.folder)
            self.assertEqual(
                sorted(e['path'] for e in entries),
                ['/originais/antigos/livro-b.pdf', '/originais/livro-a.pdf'],
                "Only blobs under the subdirectory, recursively.")
            self.folder.recursive = False
            entries = client.list_folder(self.folder)
            self.assertEqual([e['path'] for e in entries],
                             ['/originais/livro-a.pdf'],
                             "Non-recursive stops at the first level.")

    def test_share_is_the_blob_page_and_never_expires(self):
        record = self.env['liber.cloud.file'].create({
            'folder_id': self.folder.id, 'name': 'livro-a.pdf',
            'path': '/originais/livro-a.pdf'})
        with patch.object(GitHubClient, '__init__', _client_stub), \
             patch.object(GitHubClient, '_branch', return_value='main'):
            record.action_share()
        self.assertEqual(
            record.shared_link,
            'https://github.com/edlab/acervo/blob/main/originais/livro-a.pdf')
        # supports_expiration=False: the ledger honestly records no deadline,
        # whatever the account's TTL says.
        self.assertFalse(record.share_expires)
