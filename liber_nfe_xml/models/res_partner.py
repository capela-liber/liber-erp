# -*- coding: utf-8 -*-

import io
from odoo import models, fields, api, _
import base64
import datetime
import logging

_logger = logging.getLogger(__name__)


class NFeResPartner(models.Model):
    _inherit = 'res.partner'

    identification_no = fields.Char('Identification No.')
    po_tag = fields.Char('PO XML tag')
    vendor_tag = fields.Char('Vendor Order XML tag')

    def action_open_xmls(self):
        # Open XML Files for the Lead:
        xml_files = self.env['nfe.xml.panel'].search([('partner_id', '=', self.id)])
        tree_view_ref = self.env.ref('liber_nfe_xml.view_soc_xml_panel_tree', False)
        form_view_ref = self.env.ref('liber_nfe_xml.view_soc_xml_panel_form', False)
        return {
            'name': _('NFe XML Files'),
            'res_model': 'nfe.xml.panel',
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'views': [(tree_view_ref.id, 'list'), (form_view_ref.id, 'form')],
            'domain': [('id', 'in', xml_files.ids)],
            'context': {
                'default_partner_id': self.id,
                'group_by': 'status',
            }
        }


class ResCompany(models.Model):
    _inherit = 'res.company'

    nfe_xml_partner_id = fields.Many2one('res.partner', string="Default Customer from Model 65")
