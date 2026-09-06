# -*- coding: utf-8 -*-
"""The GitHub body on the chassis: registration, the tree walk, the share."""
import base64
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_github.services import github_api
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


POINTER = (b'version https://git-lfs.github.com/spec/v1\n'
           b'oid sha256:' + b'ad48' * 16 + b'\n'
           b'size 1724435\n')
OID = 'ad48' * 16


class _Resp:
    """Just enough of a requests response for the LFS conversation."""

    def __init__(self, status=200, payload=None, content=b''):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.text = ''

    def json(self):
        return self._payload


def _lfs_client():
    client = GitHubClient.__new__(GitHubClient)
    client._token = 't'
    return client


@tagged('post_install', '-at_install')
class TestGitHubLFS(TransactionCase):
    """A PDF in Git LFS is a pointer in the repository; the contents API
    hands over those hundred-odd bytes and the viewer chokes on them. The
    client must notice the pointer and go fetch the real thing."""

    def test_pointer_is_followed_to_the_real_bytes(self):
        batch = {'objects': [{'oid': OID, 'size': 1724435, 'actions': {
            'download': {'href': 'https://lfs.example/obj'}}}]}
        with patch.object(github_api.requests, 'post',
                          return_value=_Resp(payload=batch)) as post, \
             patch.object(github_api.requests, 'get',
                          return_value=_Resp(content=b'%PDF-1.3 real')) as get:
            got = _lfs_client()._lfs_fetch('edlab/acervo', OID, 1724435)
        self.assertEqual(got, b'%PDF-1.3 real',
                         "The download yields the object, not the pointer.")
        self.assertTrue(
            post.call_args[0][0].endswith(
                'github.com/edlab/acervo.git/info/lfs/objects/batch'),
            "The batch endpoint lives on github.com, not on the REST host.")
        self.assertEqual(post.call_args[1]['auth'], ('x-access-token', 't'),
                         "LFS speaks Basic, not the Bearer of the REST API.")
        self.assertEqual(get.call_args[0][0], 'https://lfs.example/obj')

    def test_download_reads_the_pointer_and_leaves_plain_files_alone(self):
        folder = self.env['liber.cloud.folder'].create({
            'name': 'LFS', 'path': '/', 'provider': 'github',
            'company_id': self.env['res.company'].create({'name': 'LFS Co'}).id,
            'external_id': 'edlab/acervo', 'github_branch': 'main'})
        record = self.env['liber.cloud.file'].create({
            'folder_id': folder.id, 'name': 'capa.pdf', 'path': '/capa.pdf'})
        with patch.object(GitHubClient, '__init__', _client_stub), \
             patch.object(GitHubClient, '_request', return_value=POINTER), \
             patch.object(GitHubClient, '_lfs_fetch',
                          return_value=b'%PDF-1.3 real') as fetch:
            self.assertEqual(GitHubClient(None).download(record),
                             b'%PDF-1.3 real')
        self.assertEqual(fetch.call_args[0], ('edlab/acervo', OID, 1724435),
                         "oid and size are read off the pointer itself.")

        # A small ordinary file is content, not a pointer: it must come
        # back untouched, without an LFS round trip.
        with patch.object(GitHubClient, '__init__', _client_stub), \
             patch.object(GitHubClient, '_request', return_value=b'%PDF-1.3 x'), \
             patch.object(GitHubClient, '_lfs_fetch') as fetch:
            self.assertEqual(GitHubClient(None).download(record), b'%PDF-1.3 x')
        fetch.assert_not_called()

    def test_malformed_pointer_is_not_mistaken_for_one(self):
        client = _lfs_client()
        self.assertIsNone(client._lfs_pointer(b'%PDF-1.3 a real file'))
        self.assertIsNone(client._lfs_pointer(
            b'version https://git-lfs.github.com/spec/v1\noid sha256:x\n'),
            "No size, no pointer -- the batch API would be asked nonsense.")
        self.assertIsNone(client._lfs_pointer(
            b'version https://git-lfs.github.com/spec/v1\n'
            b'oid sha256:' + b'a' * 64 + b'\nsize nao-e-numero\n'))
        self.assertIsNone(
            client._lfs_pointer(github_api.LFS_MAGIC + b'\n' + b'x' * 2000),
            "A file that merely opens like a pointer is still a file.")

    def test_exhausted_quota_says_so_instead_of_a_broken_file(self):
        """LFS bandwidth runs out and the batch answers without a link.
        Better a plain sentence than a PDF that will not open."""
        batch = {'objects': [{'oid': OID, 'size': 1724435, 'error': {
            'code': 403, 'message': 'This repository is over its data quota'}}]}
        with patch.object(github_api.requests, 'post',
                          return_value=_Resp(payload=batch)), \
             self.assertRaises(UserError) as caught:
            _lfs_client()._lfs_fetch('edlab/acervo', OID, 1724435)
        self.assertIn('quota', str(caught.exception))
