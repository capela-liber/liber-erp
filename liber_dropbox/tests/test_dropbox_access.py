# -*- coding: utf-8 -*-
"""The point of the module is the gate; these tests slam it a few times.

Every Dropbox call is mocked away: what is under test is who sees which
folder, who may share, and how the metadata mirror follows a sync -- none
of which needs the network.
"""
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.liber_dropbox.services.dropbox_api import DropboxClient


def _client_stub(self, env):
    # Replaces DropboxClient.__init__: no credentials needed under test.
    pass


# post_install: the module only depends on base_setup, so in the loading
# graph it sits before account & co.; at_install would run against a registry
# whose res.partner still misses their NOT NULL columns.
@tagged('post_install', '-at_install')
class TestDropboxAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_editorial = cls.env['res.groups'].create(
            {'name': 'Test Editorial'})
        cls.group_marketing = cls.env['res.groups'].create(
            {'name': 'Test Marketing'})
        cls.folder_open = cls.env['liber.dropbox.folder'].create({
            'name': 'Covers', 'path': '/Editorial/Covers',
            'read_group_ids': [(4, cls.group_marketing.id)],
            'write_group_ids': [(4, cls.group_editorial.id)],
        })
        cls.folder_closed = cls.env['liber.dropbox.folder'].create({
            'name': 'Contracts', 'path': '/Legal/Contracts',
        })
        cls.file_open = cls.env['liber.dropbox.file'].create({
            'folder_id': cls.folder_open.id, 'name': 'cover.pdf',
            'path': '/Editorial/Covers/cover.pdf',
        })
        cls.env['liber.dropbox.file'].create({
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

    def test_folder_visibility_follows_acl(self):
        Folder = self.env['liber.dropbox.folder']
        seen = Folder.with_user(self.reader).search([])
        self.assertEqual(seen, self.folder_open,
                         "A folder with no read group is managers-only.")
        seen = Folder.with_user(self.writer).search([])
        self.assertEqual(seen, self.folder_open,
                         "Write access implies read access.")

    def test_file_visibility_follows_folder(self):
        File = self.env['liber.dropbox.file']
        seen = File.with_user(self.reader).search([])
        self.assertEqual(seen.mapped('name'), ['cover.pdf'])

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
        # Nothing configured: the 30-day default deadline applies and is
        # both sent to Dropbox and recorded on the ledger.
        sent = mock_share.call_args.kwargs['expires']
        self.assertEqual(sent, self.file_open.share_expires)
        days = (self.file_open.share_expires
                - self.file_open.shared_on).total_seconds() / 86400
        self.assertAlmostEqual(days, 30, delta=0.1)

    def test_share_ttl_zero_means_eternal(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'liber_dropbox.share_ttl_days', '0')
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'create_shared_link',
                          return_value='https://www.dropbox.com/s/x/cover.pdf') as mock_share:
            self.file_open.with_user(self.writer).action_share()
        self.assertIsNone(mock_share.call_args.kwargs['expires'])
        self.assertFalse(self.file_open.share_expires)

    def test_manager_configures_but_does_not_write(self):
        """Configuring the shelf is one power, filling it is another."""
        manager = new_test_user(
            self.env, 'dropbox_manager',
            groups='base.group_user,liber_dropbox.group_liber_dropbox_manager')
        # A manager reads every folder, ACL-restricted ones included...
        both = self.folder_open + self.folder_closed
        self.assertEqual(
            self.env['liber.dropbox.folder'].with_user(manager)
                .search_count([('id', 'in', both.ids)]), 2)
        # ...but writing into Dropbox demands a write group, whoever you are.
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'create_shared_link',
                          return_value='https://x'):
            with self.assertRaises(AccessError):
                self.file_open.with_user(manager).action_share()
        # And mapping a new folder is an administrator's act, not a manager's.
        with self.assertRaises(AccessError):
            self.env['liber.dropbox.folder'].with_user(manager).create(
                {'name': 'Forbidden', 'path': '/Forbidden'})

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
        self.env['liber.dropbox.file'].search(
            [('folder_id', 'in', (self.folder_open + self.folder_closed).ids)]
        ).partner_ids = [(4, partner.id)]
        # The reader reaches one of the two linked files; the count says so.
        self.assertEqual(
            partner.with_user(self.reader).dropbox_file_count, 1)
        # No Dropbox access at all: zero, not an access error.
        outsider = new_test_user(self.env, 'no_dropbox',
                                 groups='base.group_user')
        self.assertEqual(
            partner.with_user(outsider).dropbox_file_count, 0)

    def test_download_needs_read_access(self):
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'get_temporary_link',
                          return_value='https://dl.dropbox.com/tmp/x'):
            action = self.file_open.with_user(self.reader).action_download()
            self.assertEqual(action['url'], 'https://dl.dropbox.com/tmp/x')
            closed_file = self.env['liber.dropbox.file'].search(
                [('folder_id', '=', self.folder_closed.id)])
            with self.assertRaises(AccessError):
                closed_file.with_user(self.reader).action_download()

    PNG_1PX = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
               'AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')

    def test_cron_sync_survives_a_broken_folder(self):
        """One folder failing must not starve the nightly run."""
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'list_folder',
                          side_effect=UserError('Dropbox is down')):
            self.env['liber.dropbox.folder']._cron_sync()  # must not raise

    def test_recursive_sync_skips_nested_mapping(self):
        """The wide mapping must not leak what the strict one protects."""
        self.folder_open.recursive = True
        self.env['liber.dropbox.folder'].create({
            'name': 'Restricted', 'path': '/Editorial/Covers/Restricted',
        })
        entries = [
            {'.tag': 'file', 'name': 'cover.pdf',
             'path_display': '/Editorial/Covers/cover.pdf',
             'size': 10, 'rev': 'r1', 'content_hash': 'h1',
             'client_modified': '2026-07-20T10:00:00Z'},
            {'.tag': 'file', 'name': 'draft.pdf',
             'path_display': '/Editorial/Covers/Drafts/draft.pdf',
             'size': 20, 'rev': 'r2', 'content_hash': 'h2',
             'client_modified': '2026-07-20T11:00:00Z'},
            {'.tag': 'file', 'name': 'secret.pdf',
             'path_display': '/Editorial/Covers/Restricted/secret.pdf',
             'size': 30, 'rev': 'r3', 'content_hash': 'h3',
             'client_modified': '2026-07-20T12:00:00Z'},
        ]
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'list_folder',
                          return_value=entries), \
             patch.object(DropboxClient, 'get_thumbnail_batch',
                          return_value={}):
            self.folder_open.action_sync()
        files = self.env['liber.dropbox.file'].search(
            [('folder_id', '=', self.folder_open.id)], order='name')
        # The plain subfolder came along; the separately mapped one did not.
        self.assertEqual(files.mapped('name'), ['cover.pdf', 'draft.pdf'])

    def test_sync_mirrors_and_archives(self):
        entries = [
            {'.tag': 'file', 'name': 'cover.pdf',
             'path_display': '/Editorial/Covers/cover.pdf',
             'size': 10, 'rev': 'r1', 'content_hash': 'h1',
             'client_modified': '2026-07-20T10:00:00Z'},
            {'.tag': 'file', 'name': 'back.pdf',
             'path_display': '/Editorial/Covers/back.pdf',
             'size': 20, 'rev': 'r2', 'content_hash': 'h2',
             'client_modified': '2026-07-20T11:00:00Z'},
            {'.tag': 'file', 'name': 'front.png',
             'path_display': '/Editorial/Covers/front.png',
             'size': 30, 'rev': 'r3', 'content_hash': 'h3',
             'client_modified': '2026-07-20T12:00:00Z'},
        ]
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'list_folder',
                          return_value=entries), \
             patch.object(DropboxClient, 'get_thumbnail_batch',
                          return_value={'/Editorial/Covers/front.png':
                                        self.PNG_1PX}) as mock_thumbs:
            self.folder_open.action_sync()
        files = self.env['liber.dropbox.file'].search(
            [('folder_id', '=', self.folder_open.id)], order='name')
        self.assertEqual(files.mapped('name'),
                         ['back.pdf', 'cover.pdf', 'front.png'])
        self.assertEqual(self.file_open.rev, 'r1')
        # Thumbnails are asked only for image formats, and stored.
        self.assertEqual(mock_thumbs.call_args.args[0],
                         ['/Editorial/Covers/front.png'])
        png = files.filtered(lambda f: f.name == 'front.png')
        self.assertTrue(png.thumbnail)

        # The file gone from Dropbox is archived, not erased: its shared-link
        # history is part of the ledger.
        with patch.object(DropboxClient, '__init__', _client_stub), \
             patch.object(DropboxClient, 'list_folder',
                          return_value=entries[:1]), \
             patch.object(DropboxClient, 'get_thumbnail_batch',
                          return_value={}):
            self.folder_open.action_sync()
        files = self.env['liber.dropbox.file'].search(
            [('folder_id', '=', self.folder_open.id)])
        self.assertEqual(files.mapped('name'), ['cover.pdf'])
        archived = self.env['liber.dropbox.file'].with_context(
            active_test=False).search(
            [('folder_id', '=', self.folder_open.id), ('active', '=', False)],
            order='name')
        self.assertEqual(archived.mapped('name'), ['back.pdf', 'front.png'])
