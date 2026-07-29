# -*- coding: utf-8 -*-
"""The GitHub body on the chassis: registration, the tree walk, the share."""
import base64
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

    def test_root_maps_the_whole_repository(self):
        """Path '/' is the repository root: no prefix filters the tree,
        and an upload commits at the top level."""
        # Its own company: '/' is unique per provider and company, and a
        # real mapped root may already hold the slot in this database.
        company = self.env['res.company'].create({'name': 'Raiz Co'})
        root = self.env['liber.cloud.folder'].create({
            'name': 'Teste', 'path': '/', 'provider': 'github',
            'company_id': company.id,
            'external_id': 'edlab/teste', 'github_branch': 'main'})
        tree = {'tree': [
            {'type': 'blob', 'path': 'LEIA-ME.md', 'sha': 's1', 'size': 5},
            {'type': 'blob', 'path': 'sub/livro.pdf', 'sha': 's2', 'size': 9},
        ]}
        with patch.object(GitHubClient, '__init__', _client_stub), \
             patch.object(GitHubClient, '_request', return_value=tree):
            client = GitHubClient(None)
            entries = client.list_folder(root)
            self.assertEqual([e['path'] for e in entries], ['/LEIA-ME.md'],
                             "Non-recursive root stops at the top level.")
            root.recursive = True
            self.assertEqual(
                sorted(e['path'] for e in client.list_folder(root)),
                ['/LEIA-ME.md', '/sub/livro.pdf'])

        with patch.object(GitHubClient, '__init__', _client_stub), \
             patch.object(GitHubClient, '_branch', return_value='main'), \
             patch.object(GitHubClient, '_exists', return_value=False), \
             patch.object(GitHubClient, '_request', return_value={}) as call:
            GitHubClient(None).upload(root, 'novo.md', b'x')
        self.assertEqual(call.call_args[0][1],
                         '/repos/edlab/teste/contents/novo.md',
                         "No leading slash in the committed path.")

    def test_upload_wizard_sends_every_picked_file(self):
        """The wizard takes a whole selection, one commit each, and leaves
        no copy of the bytes behind in Odoo."""
        Attachment = self.env['ir.attachment']
        picked = Attachment.create([
            {'name': '01.png', 'datas': base64.b64encode(b'one')},
            {'name': '02.png', 'datas': base64.b64encode(b'two')},
        ])
        wizard = self.env['liber.cloud.upload'].create({
            'provider': 'github', 'folder_id': self.folder.id,
            'attachment_ids': [(6, 0, picked.ids)]})
        with patch.object(GitHubClient, '__init__', _client_stub), \
             patch.object(GitHubClient, 'upload') as upload, \
             patch.object(GitHubClient, 'list_folder', return_value=[]):
            wizard.action_upload()
        self.assertEqual([call.args[1:] for call in upload.call_args_list],
                         [('01.png', b'one'), ('02.png', b'two')],
                         "Every picked file travels, under its own name.")
        self.assertFalse(picked.exists(),
                         "The staged attachments are dropped after sending.")

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
