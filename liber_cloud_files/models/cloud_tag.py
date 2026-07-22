# -*- coding: utf-8 -*-
from odoo import fields, models


class LiberCloudTag(models.Model):
    """One vocabulary for the whole house, across providers.

    'contrato' is 'contrato' on any shelf. Tags are curated by managers
    per company (an empty company means every company sees it).
    """
    _name = 'liber.cloud.tag'
    _description = 'Cloud File Tag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer()
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company,
        help="Leave empty to share the tag with every company.")
    active = fields.Boolean(default=True)

    _name_company_uniq = models.Constraint(
        'unique(name, company_id)', 'This tag already exists.')
