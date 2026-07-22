# -*- coding: utf-8 -*-
"""The point of the chassis is the gate; these tests slam it a few times.

Every Dropbox call is mocked away: what is under test is who sees which
folder, who may share, how the metadata mirror follows a sync, and where
the company walls stand -- none of which needs the network.
"""
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.liber_dropbox.services.dropbox_api import DropboxClient


def _client_stub(self, account):
    # Replaces DropboxClient.__init__: no credentials needed under test.
    pass


# post_install: the chassis only depends on base_setup/product, so in the
# loading graph it sits before account & co.; at_install would run against
# a registry whose res.partner still misses their NOT NULL columns.
@tagged('post_install', '-at_install')
class TestDropboxAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # The database under test may already hold the company's real
        # account (unique per provider × company): reuse it then.
        Account = cls.env['liber.cloud.account']
        cls.account = Account.search([
            ('provider', '=', 'dropbox'),
            ('company_id', '=', cls.company.id)], limit=1) or Account.create({
                'provider': 'dropbox', 'company_id': cls.company.id,
                'dropbox_app_key': 'k', 'dropbox_app_secret': 's',
                'dropbox_refresh_token': 'r',
            })
        cls.account.share_ttl_days = 30
        cls.group_editorial = cls.env['res.groups'].create(
            {'name': 'Test Editorial'})
        cls.group_marketing = cls.env['res.groups'].create(
            {'name': 'Test Marketing'})
        cls.folder_open = cls.env['liber.cloud.folder'].create({
            'name': 'Covers', 'path': '/Editorial/Covers',
            'provider': 'dropbox',
            'read_group_ids': [(4, cls.group_marketing.id)],
            'write_group_ids': [(4, cls.group_editorial.id)],
        })
        cls.folder_closed = cls.env['liber.cloud.folder'].create({
            'name': 'Contracts', 'path': '/Legal/Contracts',
            'provider': 'dropbox',
        })
        cls.file_open = cls.env['liber.cloud.file'].create({
            'folder_id': cls.folder_open.id, 'name': 'cover.pdf',
            'path': '/Editorial/Covers/cover.pdf',
        })
        cls.env['liber.cloud.file'].create({
            'folder_id': cls.folder_closed.id, 'name': 'contract.pdf',
            'path': '/Legal/Contracts/contract.pdf',
        })
        cls.reader = new_test_user(
            cls.env, 'dropbox_reader',
            groups='base.group_user,liber_dropbox.group_liber_dropbox_user')
        cls.reader.group_ids += cls.group_marketing
        cls.writer = new_test_user(
            cls.env, 'dropbox_writer',
            groups='base.group_user,liber_dropbox.group_liber_dropbox_user')
        cls.writer.group_ids += cls.group_editorial

    # ------------------------------------------------------------------
    # the folder ACL
    # ------------------------------------------------------------------
    def test_folder_visibility_follows_acl(self):
        Folder = self.env['liber.cloud.folder']
        seen = Folder.with_user(self.reader).search([])
        self.assertEqual(seen, self.folder_open,
                         "A folder with no read group is managers-only.")
        seen = Folder.with_user(self.writer).search([])
        self.assertEqual(seen, self.folder_open,
                         "Write access implies read access.")

    def test_file_visibility_follows_folder(self):
        File = self.env['liber.cloud.file']
        seen = File.with_user(self.reader).search([])
        self.assertEqual(seen.mapped('name'), ['cover.pdf'])

    def test_manager_configures_but_does_not_write(self):
        """Configuring the shelf is one power, filling it is another."""
        manager = new_test_user(
            self.env, 'dropbox_manager',
            groups='base.group_user,liber_dropbox.group_liber_dropbox_manager')
        both = self.folder_open + self.folder_closed
        self.assertEqual(
            self.env['liber.cloud.folder'].with_user(manager)
                .search_count([('id', 'in', both.ids)]), 2)
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'create_shared_link',
                          return_value='https://x'):
            with self.assertRaises(AccessError):
                self.file_open.with_user(manager).action_share()
        with self.assertRaises(AccessError):
            self.env['liber.cloud.folder'].with_user(manager).create(
                {'name': 'Forbidden', 'path': '/Forbidden',
                 'provider': 'dropbox'})

    def test_linking_needs_folder_write(self):
        partner = self.env['res.partner'].create({'name': 'Author'})
        with self.assertRaises(AccessError):
            self.file_open.with_user(self.reader).partner_ids = [
                (4, partner.id)]
        self.file_open.with_user(self.writer).partner_ids = [(4, partner.id)]
        self.assertEqual(self.file_open.partner_ids, partner)

    def test_partner_file_count_respects_acl(self):
        """The smart-button count promises only what the rules will open."""
        partner = self.env['res.partner'].create({'name': 'Author'})
        self.env['liber.cloud.file'].search(
            [('folder_id', 'in', (self.folder_open + self.folder_closed).ids)]
        ).partner_ids = [(4, partner.id)]
        self.assertEqual(
            partner.with_user(self.reader).cloud_file_count, 1)
        outsider = new_test_user(self.env, 'no_dropbox',
                                 groups='base.group_user')
        self.assertEqual(
            partner.with_user(outsider).cloud_file_count, 0)

    # ------------------------------------------------------------------
    # sharing and downloading
    # ------------------------------------------------------------------
    def test_share_needs_write_access(self):
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'create_shared_link',
                          return_value='https://www.dropbox.com/s/x/cover.pdf') as mock_share:
            with self.assertRaises(AccessError):
                self.file_open.with_user(self.reader).action_share()
            self.file_open.with_user(self.writer).action_share()
        self.assertEqual(self.file_open.shared_link,
                         'https://www.dropbox.com/s/x/cover.pdf')
        self.assertEqual(self.file_open.shared_by_id, self.writer)
        # The account's 30-day default deadline applies and is both sent
        # to Dropbox and recorded on the ledger.
        sent = mock_share.call_args.kwargs['expires']
        self.assertEqual(sent, self.file_open.share_expires)
        days = (self.file_open.share_expires
                - self.file_open.shared_on).total_seconds() / 86400
        self.assertAlmostEqual(days, 30, delta=0.1)

    def test_share_ttl_zero_means_eternal(self):
        self.account.share_ttl_days = 0
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'create_shared_link',
                          return_value='https://www.dropbox.com/s/x/cover.pdf') as mock_share:
            self.file_open.with_user(self.writer).action_share()
        self.assertIsNone(mock_share.call_args.kwargs['expires'])
        self.assertFalse(self.file_open.share_expires)

    def test_download_needs_read_access(self):
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'temporary_link',
                          return_value='https://dl.dropbox.com/tmp/x'):
            action = self.file_open.with_user(self.reader).action_download()
            self.assertEqual(action['url'], 'https://dl.dropbox.com/tmp/x')
            closed_file = self.env['liber.cloud.file'].search(
                [('folder_id', '=', self.folder_closed.id)])
            with self.assertRaises(AccessError):
                closed_file.with_user(self.reader).action_download()

    # ------------------------------------------------------------------
    # the mirror
    # ------------------------------------------------------------------
    PNG_1PX = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
               'AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')

    def test_sync_mirrors_and_archives(self):
        entries = [
            {'name': 'cover.pdf', 'path': '/Editorial/Covers/cover.pdf',
             'size': 10, 'rev': 'r1', 'content_hash': 'h1',
             'client_modified': '2026-07-20 10:00:00'},
            {'name': 'back.pdf', 'path': '/Editorial/Covers/back.pdf',
             'size': 20, 'rev': 'r2', 'content_hash': 'h2',
             'client_modified': '2026-07-20 11:00:00'},
            {'name': 'front.png', 'path': '/Editorial/Covers/front.png',
             'size': 30, 'rev': 'r3', 'content_hash': 'h3',
             'client_modified': '2026-07-20 12:00:00'},
        ]
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'list_folder',
                          return_value=entries), \
             patch.object(DropboxClient, 'get_thumbnail_batch',
                          return_value={'/Editorial/Covers/front.png':
                                        self.PNG_1PX}) as mock_thumbs:
            self.folder_open.action_sync()
        files = self.env['liber.cloud.file'].search(
            [('folder_id', '=', self.folder_open.id)], order='name')
        self.assertEqual(files.mapped('name'),
                         ['back.pdf', 'cover.pdf', 'front.png'])
        self.assertEqual(self.file_open.rev, 'r1')
        # Thumbnails were asked only for the image, and stored.
        self.assertEqual(mock_thumbs.call_args.args[0].mapped('path'),
                         ['/Editorial/Covers/front.png'])
        png = files.filtered(lambda f: f.name == 'front.png')
        self.assertTrue(png.thumbnail)

        # The file gone from Dropbox is archived, not erased: its
        # shared-link history is part of the ledger.
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'list_folder',
                          return_value=entries[:1]), \
             patch.object(DropboxClient, 'get_thumbnail_batch',
                          return_value={}):
            self.folder_open.action_sync()
        files = self.env['liber.cloud.file'].search(
            [('folder_id', '=', self.folder_open.id)])
        self.assertEqual(files.mapped('name'), ['cover.pdf'])
        archived = self.env['liber.cloud.file'].with_context(
            active_test=False).search(
            [('folder_id', '=', self.folder_open.id), ('active', '=', False)],
            order='name')
        self.assertEqual(archived.mapped('name'), ['back.pdf', 'front.png'])

    def test_client_excludes_nested_mapping(self):
        """The wide mapping must not leak what the strict one protects."""
        self.folder_open.recursive = True
        nested = self.env['liber.cloud.folder'].create({
            'name': 'Restricted', 'path': '/Editorial/Covers/Restricted',
            'provider': 'dropbox'})
        payload = {'has_more': False, 'entries': [
            {'.tag': 'file', 'name': 'cover.pdf',
             'path_display': '/Editorial/Covers/cover.pdf', 'rev': 'r1'},
            {'.tag': 'file', 'name': 'draft.pdf',
             'path_display': '/Editorial/Covers/Drafts/draft.pdf',
             'rev': 'r2'},
            {'.tag': 'file', 'name': 'secret.pdf',
             'path_display': '/Editorial/Covers/Restricted/secret.pdf',
             'rev': 'r3'},
        ]}
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, '_call', return_value=payload):
            client = DropboxClient(None)
            entries = client.list_folder(self.folder_open, exclude=nested)
        # The plain subfolder came along; the separately mapped one did not.
        self.assertEqual(sorted(e['name'] for e in entries),
                         ['cover.pdf', 'draft.pdf'])

    def test_cron_sync_survives_a_broken_folder(self):
        """One folder failing must not starve the nightly run."""
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'list_folder',
                          side_effect=UserError('Dropbox is down')):
            self.env['liber.cloud.folder']._cron_sync()  # must not raise

    # ------------------------------------------------------------------
    # multicompany
    # ------------------------------------------------------------------
    def test_company_wall(self):
        """Matching groups in the wrong company open nothing."""
        company2 = self.env['res.company'].create({'name': 'Filial'})
        folder2 = self.env['liber.cloud.folder'].with_company(company2).create({
            'name': 'Covers B', 'path': '/Editorial/Covers',
            'provider': 'dropbox', 'company_id': company2.id,
            'read_group_ids': [(4, self.group_marketing.id)],
        })
        self.env['liber.cloud.file'].create({
            'folder_id': folder2.id, 'name': 'other.pdf',
            'path': '/Editorial/Covers/other.pdf'})
        # The reader is in the right group but the wrong company.
        seen = self.env['liber.cloud.folder'].with_user(self.reader).search([])
        self.assertNotIn(folder2, seen)
        seen = self.env['liber.cloud.file'].with_user(self.reader).search([])
        self.assertEqual(seen.mapped('name'), ['cover.pdf'])
        # Granted the company, the same groups open the folder.
        self.reader.company_ids += company2
        seen = self.env['liber.cloud.folder'].with_user(self.reader).search([])
        self.assertIn(folder2, seen)

    def test_account_is_per_company(self):
        """A company without its own credential cannot sync."""
        company2 = self.env['res.company'].create({'name': 'Filial'})
        folder2 = self.env['liber.cloud.folder'].create({
            'name': 'Covers B', 'path': '/Editorial/Covers',
            'provider': 'dropbox', 'company_id': company2.id,
        })
        with self.assertRaises(UserError):
            folder2._account()
        account2 = self.env['liber.cloud.account'].create({
            'provider': 'dropbox', 'company_id': company2.id})
        self.assertEqual(folder2._account(), account2)
        self.assertEqual(self.folder_open._account(), self.account)
