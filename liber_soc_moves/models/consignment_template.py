# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ConsignmentTemplate(models.Model):
    _name = 'consignment.template'
    _description = 'Consignment Campaign'
    _order = 'name'

    name = fields.Char(string='Campaign', required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company)
    note = fields.Text(string='Notes')
    line_ids = fields.One2many(
        'consignment.template.line', 'template_id', string='Products')
    product_count = fields.Integer(compute='_compute_product_count', string='# Products')

    @api.depends('line_ids')
    def _compute_product_count(self):
        for tmpl in self:
            tmpl.product_count = len(tmpl.line_ids)


class ConsignmentTemplateLine(models.Model):
    _name = 'consignment.template.line'
    _description = 'Consignment Campaign Line'

    template_id = fields.Many2one(
        'consignment.template', string='Campaign', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain=[('type', '=', 'consu')])
    product_uom_qty = fields.Integer(string='Quantity', default=1, required=True)
