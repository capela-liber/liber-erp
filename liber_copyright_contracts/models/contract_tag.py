# -*- coding: utf-8 -*-
from odoo import fields, models


class EdlabContractTag(models.Model):
    _name = "edlab.contract.tag"
    _description = "Contract Tag"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(string="Color")

    _sql_constraints = [
        ("name_uniq", "unique(name)", "This tag already exists."),
    ]
