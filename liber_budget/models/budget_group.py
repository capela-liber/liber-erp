# -*- coding: utf-8 -*-
from odoo import fields, models


class BudgetGroup(models.Model):
    _name = 'budget.group'
    _description = "Budget Group"
    _order = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', string="Company",
        default=lambda self: self.env.company)


class BudgetTag(models.Model):
    _name = 'budget.tag'
    _description = "Budget Tag"
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer(string="Color")
