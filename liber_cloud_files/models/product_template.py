# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    cloud_file_count = fields.Integer(compute='_compute_cloud_file_count')

    def _compute_cloud_file_count(self):
        # Deliberately NOT compute_sudo: the count must match what the
        # record rules will let this user open, folder ACLs included.
        File = self.env['liber.cloud.file']
        if not File.has_access('read'):
            self.cloud_file_count = 0
            return
        data = File._read_group(
            [('product_tmpl_id', 'in', self.ids)],
            ['product_tmpl_id'], ['__count'])
        counts = {template.id: count for template, count in data}
        for record in self:
            record.cloud_file_count = counts.get(record.id, 0)

    def action_view_cloud_files(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'liber_cloud_files.action_liber_cloud_file')
        action['domain'] = [('product_tmpl_id', '=', self.id)]
        action['context'] = {'default_product_tmpl_id': self.id}
        return action
