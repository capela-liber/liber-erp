# -*- coding: utf-8 -*-
"""The chatter on a GitHub file, on the real screen, as a reader.

`CloudGateCase` proves in the ORM that a reader may comment without being
able to edit. This proves the screen: that the file's form opens for the
reader, that the chatter renders on it, and that a note goes through --
the form reads more than the test asks, and only the tour sees that.
"""
from odoo.tests import HttpCase, tagged

#: login and password of the tour user; the password references it (see
#: CLAUDE.md: a literal would trip the secret scan of the publish).
LOGIN = 'github_reader_tour'


@tagged('post_install', '-at_install', 'liber_github_tour')
class TestCloudFileChatterTour(HttpCase):

    def test_cloud_file_chatter_tour(self):
        company = self.env.company
        role = self.env['res.groups'].create({'name': 'Tour role: reads'})
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'GitHub Reader of the Tour',
            'login': LOGIN,
            'password': LOGIN,
            'lang': 'en_US',
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('liber_github.group_liber_github_user').id),
                (4, role.id),
            ],
        })
        Account = self.env['liber.cloud.account']
        if not Account.search([('provider', '=', 'github'),
                               ('company_id', '=', company.id)]):
            Account.create({'provider': 'github', 'company_id': company.id,
                            'github_token': 't'})
        folder = self.env['liber.cloud.folder'].create({
            'name': 'Tour shelf', 'provider': 'github',
            'path': '/tour', 'external_id': 'edlab/tour',
            'read_group_ids': [(4, role.id)],
        })
        self.env['liber.cloud.file'].create({
            'folder_id': folder.id, 'name': 'TOUR_CAPA.pdf',
            'path': '/tour/TOUR_CAPA.pdf',
        })
        self.start_tour('/odoo', 'cloud_file_chatter_tour', login=LOGIN)
