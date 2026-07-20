# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime
import re
import xml.etree.ElementTree as ET
import base64
import logging
_logger = logging.getLogger(__name__)


class SocXmlPanelAttachment(models.Model):
    _inherit = 'ir.attachment'

    # LAB FORK / Odoo 19: the 'active' field was removed - ir.attachment
    # forbids an active/archive flag now (hard assert in _search). The
    # nfe_xml_processed flag alone marks attachments already turned into
    # panels.
    status = fields.Selection([
        ('draft', 'Draft'),
        ('issue', 'issue'),
        ('done', 'done'),
    ], string='Status', default='draft',)
    nfe_xml_processed = fields.Boolean("NFe XML Processed")

    def create_nfe_xml_panel_cron(self):
        # Cron to create NFe XML Panel every day from the attachments having xml:
        date = datetime.strptime('01/01/20 00:00:00', '%m/%d/%y %H:%M:%S')
        # date = (datetime.now() - timedelta(days=1)).strftime('%m/%d/%y ') + '00:00:00'
        search_limit = self.env['ir.config_parameter'].sudo().get_param('nfe_xml_search_limit', default='100')
        search_limit = re.sub('[^0-9]', '', search_limit or '')
        if search_limit:
            search_limit = int(search_limit)
        else:
            search_limit = 100

        soc_xmls = self.env['ir.attachment'].sudo().search([('name', 'ilike', 'procnfe.xml' and 'nfe.xml'),
                                                     ('name', 'not ilike', 'nfe-ret'),
                                                     ('name', 'not ilike', 'Danfe.xml'),
                                                     ('create_date', '>=', date),
                                                     ('res_model', 'not in', ('nfe.xml.panel', 'account.move')),
                                                     ('datas', '!=', ''),
                                                     ('nfe_xml_processed', '=', False),
                                                     ], limit=search_limit)
        for file in soc_xmls:
            #Check for Duplicate Files:
            _logger.info('11111 File ( %s) and   File name (%s)' % (file, file.name))
            duplicate_files = self.env['ir.attachment'].sudo().search_count(
                [('nfe_xml_processed', '=', True), ('name', '=', file.name)])
            _logger.info('222222222222 %s | %s' % (duplicate_files, file))
            if not duplicate_files:
                #Create if no dupliacte file exist:
                soc_data = self.env['nfe.xml.panel'].create({
                    # 'partner_id': file.partner_id.id if file.partner_id else False,
                    'file_name': file.name,
                    'file': file.datas,
                    'related_res_id': file.res_id if file.res_id else False,
                    'related_res_model': file.res_model if file.res_model else False,
                    'related_attachment_id': file.id,
                    'system_generated': True,
                    'source': 'attachment',
                })
                _logger.info('================START==================')  # debug
                if soc_data:
                    _logger.info('1 ----- file ---- %s', soc_data)  # debug
                    msg1 = _("This record created from NFe XML Cron")
                    _logger.info('2 ----- MSG ---- %s', msg1)  # debug
                    try:
                        soc_data.sudo().message_post(body=msg1)
                        channel_id = self.env.ref('liber_nfe_xml.channel_xml')
                        channel_id.message_post(
                            subject=_('New XML File!!'),
                            body=(_('''Hi... <br>
                                                                        New XML file is Arrived : %s <br>
                                                                        <b>Customer : %s <br> </b>''') %
                                  (soc_data.sudo().display_name, (soc_data.sudo().partner_id.name or ''))),
                            subtype_xmlid='mail.mt_comment')
                        file.nfe_xml_processed = True
                    except Exception as e:
                        file.nfe_xml_processed = True
                        logging.info('Bad Request')
                        _logger.info('3 ----- MSG Post Issue ---- %s', e)  #
                        file.write({'status': 'issue'})
                        # file.message_post(body="Cron Issue: This file having some issues.")
                        return False

                    if soc_data.related_res_id and soc_data.related_res_model:
                        msg = _(
                            "Record of XML File : <a href=# data-oe-model=%s data-oe-id=%d>%s</a>") \
                              % (soc_data.related_res_model, int(soc_data.related_res_id), "Attached Record")

                        soc_data.message_post(body=msg)
                        msg2 = _(
                            "Attachment of XML File : <a href=# data-oe-model=ir.attachment data-oe-id=%d>%s</a>") \
                              % (int(soc_data.related_attachment_id), "Attachment")
                        soc_data.message_post(body=msg2)

                else:
                    _logger.info('3 ----- Not Created ---- ')
                    file.write({'status': 'issue'})
                    # file.message_post(body="Cron Issue: This file having some issues.")
                _logger.info('================END==================')
            else:
                file.nfe_xml_processed = True
                _logger.info('------------Duplicate File-----------')

    # Read the XML Files:-
    def read_file(self, data):
        dict = {
            'partner_id': '',
            'cfop_id': '',
            'date': '',
            'company_id': ''
        }
        for record in data:
            _logger.info('===== Read XML Start %s =====', record.id)
            # LAB FORK / Odoo 19: parse in memory (the temp-file version
            # never flushed before parsing).
            if record.file:
                root = ET.fromstring(base64.b64decode(record.file))
                cnpj = ''
                company_cnpj = ''
                cfop = ''
                # GET fields for XML Panel :-
                if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                                               '{http://www.portalfiscal.inf.br/nfe}enviNFe']:

                    #Get partner by reading file :
                    try:
                        emit = root.find('.//{http://www.portalfiscal.inf.br/nfe}emit')
                        if emit.tag:
                            cnpj = emit.find('.//{http://www.portalfiscal.inf.br/nfe}CNPJ').text
                    except Exception as e:
                        return False
                    if len(cnpj) > 1:
                        cnpj_cpf = '{}{}.{}{}{}.{}{}{}/{}{}{}{}-{}{}'.format(*cnpj)
                        partner_id = self.env['res.partner'].search(
                            ['|', ('vat', '=', cnpj_cpf), ('vat', '=', cnpj)], limit=1)
                        if partner_id:
                            _logger.info('===== Read partner end %s=====', partner_id.id)
                            dict['partner_id'] = partner_id.id

                    # Get CFOP by reading file :
                    try:
                        cfop = root.find('.//{http://www.portalfiscal.inf.br/nfe}CFOP').text
                    except Exception as e:
                        return False
                    if len(cfop) > 1:
                        cfop_id = self.env['nfe.cfop'].search([('code', '=', cfop)], limit=1)
                        if cfop_id:
                            dict['cfop_id'] = cfop_id.id
                    #Get date :-
                    try:
                        date = root.find('.//{http://www.portalfiscal.inf.br/nfe}dhEmi').text
                    except Exception as e:
                        return False
                    if date:
                        dict['date'] = date[0:10]

                    # Get Company by reading file :
                    try:
                        dest = root.find('.//{http://www.portalfiscal.inf.br/nfe}dest')
                        if dest.tag:
                            company_cnpj = dest.find('.//{http://www.portalfiscal.inf.br/nfe}CNPJ').text
                    except Exception as e:
                        return False
                    if len(company_cnpj) > 1:
                        company = '{}{}.{}{}{}.{}{}{}/{}{}{}{}-{}{}'.format(*company_cnpj)
                        partner = self.env['res.partner'].sudo().search(['|', ('vat', '=', company),
                                                                         ('vat', '=', company_cnpj)], limit=1)
                        if partner and partner.company_id:
                            _logger.info('===== Read XML company end %s=====', partner.company_id)
                            dict['company_id'] = partner.company_id.id

        return dict
