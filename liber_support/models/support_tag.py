# -*- coding: utf-8 -*-
from odoo import fields, models


class SupportTag(models.Model):
    _name = 'liber.support.tag'
    _description = 'Support Tag'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(string='Color')

    _name_uniq = models.Constraint(
        'UNIQUE (name)', 'Tag name already exists.')
