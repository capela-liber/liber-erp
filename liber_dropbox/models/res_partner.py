# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dropbox_file_count = fields.Integer(
        compute='_compute_dropbox_file_count')

    def _compute_dropbox_file_count(self):
        # Deliberately NOT compute_sudo: the count must match what the
        # record rules will let this user open, folder ACLs included.
        File = self.env['liber.dropbox.file']
        if not File.has_access('read'):
            self.dropbox_file_count = 0
            return
        data = File._read_group(
            [('partner_ids', 'in', self.ids)], ['partner_ids'], ['__count'])
        counts = {partner.id: count for partner, count in data}
        for record in self:
            record.dropbox_file_count = counts.get(record.id, 0)

    def action_view_dropbox_files(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'liber_dropbox.action_liber_dropbox_file')
        action['domain'] = [('partner_ids', 'in', self.id)]
        action['context'] = {'default_partner_ids': [self.id]}
        return action
