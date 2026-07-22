# -*- coding: utf-8 -*-
from odoo import fields, models


class LiberDropboxTag(models.Model):
    """Free classification across folders: 'contrato', 'capa', 'PNLD'.

    Folders say where a file lives and who reaches it; tags say what it
    is, regardless of where. The vocabulary is curated by managers so it
    stays a vocabulary, not a swamp.
    """
    _name = 'liber.dropbox.tag'
    _description = 'Dropbox File Tag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer()
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)', 'This tag already exists.')
