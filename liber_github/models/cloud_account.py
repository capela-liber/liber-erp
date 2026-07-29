# -*- coding: utf-8 -*-
from odoo import fields, models


class LiberCloudAccount(models.Model):
    _inherit = 'liber.cloud.account'

    provider = fields.Selection(
        selection_add=[('github', 'GitHub')],
        ondelete={'github': 'cascade'})
    github_token = fields.Char(
        string='Access Token',
        help="A fine-grained personal access token, created on the personal "
             "GitHub account of an organization member (Settings > Developer "
             "settings > Personal access tokens > Fine-grained tokens), with "
             "the organization as Resource owner and Contents read/write on "
             "the mapped repositories; see the module's NOTES.md.")
