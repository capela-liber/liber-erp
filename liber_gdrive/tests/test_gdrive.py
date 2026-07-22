# -*- coding: utf-8 -*-
"""The Drive body on the chassis: registration, and the ID-based walk."""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_gdrive.services.gdrive_api import GDriveClient


def _client_stub(self, account):
    pass


@tagged('post_install', '-at_install')
class TestGDrive(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['liber.cloud.account']
        cls.account = Account.search([
            ('provider', '=', 'gdrive'),
            ('company_id', '=', cls.env.company.id)], limit=1) or \
            Account.create({
                'provider': 'gdrive', 'company_id': cls.env.company.id,
                'gdrive_client_id': 'i', 'gdrive_client_secret': 's',
                'gdrive_refresh_token': 'r'})
        cls.folder = cls.env['liber.cloud.folder'].create({
            'name': 'Financeiro', 'path': '/Financeiro',
            'provider': 'gdrive', 'external_id': 'ROOT123',
            'recursive': True})

    def test_provider_registered(self):
        client = self.env['liber.cloud.provider']._client(self.account)
        self.assertIsInstance(client, GDriveClient)
        self.assertEqual(
            self.env['liber.cloud.provider']._manager_group('gdrive'),
            'liber_gdrive.group_liber_gdrive_manager')

    def test_folder_needs_external_id(self):
        naked = self.env['liber.cloud.folder'].create({
            'name': 'Sem ID', 'path': '/SemID', 'provider': 'gdrive'})
        with patch.object(GDriveClient, '__init__', _client_stub):
            client = GDriveClient(None)
            with self.assertRaises(UserError):
                client.list_folder(naked)

    def test_list_walks_by_id_and_skips_nested_mapping(self):
        nested = self.env['liber.cloud.folder'].create({
            'name': 'Restrita', 'path': '/Financeiro/Restrita',
            'provider': 'gdrive', 'external_id': 'SUB999'})
        pages = {
            'ROOT123': {'files': [
                {'id': 'F1', 'name': 'plano.pdf', 'mimeType': 'application/pdf',
                 'size': '10', 'md5Checksum': 'h1',
                 'modifiedTime': '2026-07-20T10:00:00.000Z'},
                {'id': 'SUB111', 'name': 'Notas',
                 'mimeType': 'application/vnd.google-apps.folder'},
                {'id': 'SUB999', 'name': 'Restrita',
                 'mimeType': 'application/vnd.google-apps.folder'},
            ]},
            'SUB111': {'files': [
                {'id': 'F2', 'name': 'nota.pdf', 'mimeType': 'application/pdf',
                 'size': '20', 'md5Checksum': 'h2',
                 'modifiedTime': '2026-07-20T11:00:00.000Z'},
            ]},
        }

        def fake_request(self_, method, url, **kwargs):
            parent = kwargs['params']['q'].split("'")[1]
            return pages[parent]

        with patch.object(GDriveClient, '__init__', _client_stub), \
             patch.object(GDriveClient, '_request', fake_request):
            client = GDriveClient(None)
            entries = client.list_folder(self.folder, exclude=nested)
        self.assertEqual(
            sorted((e['name'], e['path']) for e in entries),
            [('nota.pdf', '/Financeiro/Notas/nota.pdf'),
             ('plano.pdf', '/Financeiro/plano.pdf')])
        self.assertEqual(entries[0]['client_modified'],
                         '2026-07-20 10:00:00')

    def test_no_temporary_link_means_streaming(self):
        """Drive downloads must route through Odoo's own door."""
        record = self.env['liber.cloud.file'].create({
            'folder_id': self.folder.id, 'name': 'plano.pdf',
            'path': '/Financeiro/plano.pdf', 'external_id': 'F1'})
        with patch.object(GDriveClient, '__init__', _client_stub), \
             patch.object(GDriveClient, 'temporary_link',
                          return_value=None):
            action = record.action_download()
        self.assertEqual(action['url'],
                         '/liber_cloud/download/%d' % record.id)
