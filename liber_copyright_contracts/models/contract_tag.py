# -*- coding: utf-8 -*-
from odoo import fields, models


class EdlabContractTag(models.Model):
    _name = "edlab.contract.tag"
    _description = "Contract Tag"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(string="Color")

    # v19: `_sql_constraints` não é mais suportado; ver royalty_line.py.
    _name_uniq = models.Constraint("unique(name)", "This tag already exists.")
