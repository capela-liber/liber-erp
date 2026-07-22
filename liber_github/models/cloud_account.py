# -*- coding: utf-8 -*-
from odoo import fields, models


class LiberCloudAccount(models.Model):
    _inherit = 'liber.cloud.account'

    provider = fields.Selection(
        selection_add=[('github', 'GitHub')],
        ondelete={'github': 'cascade'})
    github_token = fields.Char(
        string='Access Token',
        help="A fine-grained personal access token of the company's "
             "GitHub account, with Contents read/write on the mapped "
             "repositories; see the module's NOTES.md.")
