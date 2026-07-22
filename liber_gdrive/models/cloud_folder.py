# -*- coding: utf-8 -*-
from odoo import fields, models


class LiberCloudFolder(models.Model):
    _inherit = 'liber.cloud.folder'

    provider = fields.Selection(
        selection_add=[('gdrive', 'Google Drive')],
        ondelete={'gdrive': 'cascade'})


class LiberCloudUpload(models.TransientModel):
    _inherit = 'liber.cloud.upload'

    provider = fields.Selection(
        selection_add=[('gdrive', 'Google Drive')],
        ondelete={'gdrive': 'cascade'})
