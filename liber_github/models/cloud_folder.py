# -*- coding: utf-8 -*-
from odoo import fields, models


class LiberCloudFolder(models.Model):
    _inherit = 'liber.cloud.folder'

    provider = fields.Selection(
        selection_add=[('github', 'GitHub')],
        ondelete={'github': 'cascade'})
    github_branch = fields.Char(
        string='Branch',
        help="The branch this folder mirrors and commits to. Empty means "
             "the repository's default branch.")


class LiberCloudUpload(models.TransientModel):
    _inherit = 'liber.cloud.upload'

    provider = fields.Selection(
        selection_add=[('github', 'GitHub')],
        ondelete={'github': 'cascade'})
