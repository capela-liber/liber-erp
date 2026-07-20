# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from random import randint
import base64
import re
from datetime import date
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)
import xml.etree.ElementTree as ET


class SocXmlPanel(models.Model):
    _name = 'nfe.xml.panel'
    _description = "NFe XML Panel"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']

    # name = fields.Char('sequence')
    # Business view (derived from the fiscal roles by identify_parties):
    # partner_id is always the COUNTERPARTY (the client/supplier), never us.
    partner_id = fields.Many2one('res.partner', string='Client', readonly=False, tracking=True)
    status = fields.Selection(
        [
            ('imported', 'Imported'),
            ('valid', 'Valid'),
            ('cancelled', 'Cancelled'),
            ('error', 'Error'),
        ], string='Status', required=True, default='imported',
        tracking=True, copy=False,
        help="Imported: raw XML, not parsed yet. Valid: parsed and standing. "
             "Cancelled: a cancellation event exists. Error: parsing failed.")
    file = fields.Binary(string='XML File', attachment=True, required=True, store=True)
    file_excel = fields.Binary(string='Excel File', attachment=True, store=True)
    file_excel_name = fields.Char('EXCEL File Name')
    file_name = fields.Char('XML File Name')

    order_id = fields.Many2one('sale.order', string='Sale Order', tracking=True)
    po_id = fields.Many2one('purchase.order', string='Purchase Order', tracking=True)
    invoice_id = fields.Many2one('account.move', string='Bill/Invoice', tracking=True)
    move_ids = fields.One2many(
        'account.move', 'nfe_xml_panel_id', string='Invoices/Bills',
        help="Every invoice or bill linked to this XML through the NFe "
             "access key.")
    move_count = fields.Integer(compute='_compute_move_count')

    # Standard Odoo record company (multi-company security) AND the business
    # "our company": set at import to the fiscal side whose CNPJ matches one of
    # our res.company records (see identify_parties). The multi-company record
    # rule filters panels by this field, so a user sees only the XMLs of the
    # company they are logged into - which is why a separate "Our Company"
    # field is redundant and no longer exists.
    company_id = fields.Many2one('res.company', string='Company', tracking=True)
    related_attachment_id = fields.Char('Attachment ID')
    related_res_id = fields.Char('Resource ID')
    related_res_model = fields.Char('Resource Model')
    cfop_id = fields.Many2one('nfe.cfop', 'CFOP')

    file_create_date = fields.Date("XML Date")

    danfe_no = fields.Char('Danfe No.')
    danfe_value = fields.Float('Danfe Value')

    panel_items = fields.One2many('nfe.xml.items', 'soc_xml_id')
    due_date = fields.Date(string='XML Due Date')
    shipping_price = fields.Float(string='Shipping Price')

    # Fiscal roles, raw from the XML (Emitente / Destinatario). These are the
    # immutable fiscal facts; the business view (our company / client) is
    # derived from them in identify_parties().
    vendor_id = fields.Many2one('res.partner', string='Sender Name')
    vendor_cnpj = fields.Char(string='Issuer CNPJ')
    vendor_name = fields.Char(string='Issuer Name')
    customer_id = fields.Many2one('res.partner', string='Receiver Name')
    customer_cnpj = fields.Char(string='Recipient CNPJ')
    customer_name = fields.Char(string='Recipient Name')
    key = fields.Char(string="Nfe Key", index='btree_not_null', copy=False,
                      help="44-digit NFe access key (chave de acesso). This "
                           "is the business key that links the XML to the "
                           "invoices/bills created from it.")
    # LAB FORK: edoo_mde_id (edoo.mde) and edoc_id (eletronic.document)
    # removed - those models belong to the production-only edoo/l10n_br stack.

    system_generated = fields.Boolean(string='System generated', default=False)
    # Provenance. The panel is source-agnostic by design (an XML is an XML,
    # whoever produced it), but knowing WHICH adapter ingested a note is what
    # makes a bad import auditable instead of a mystery. Integration modules
    # extend this selection (see the `olist` module).
    source = fields.Selection(
        [('manual', 'Manual Upload'), ('attachment', 'Attachment Cron')],
        string='Source', default='manual', copy=False, tracking=True,
        help="Adapter that ingested this XML.")
    purchase_id = fields.Many2one('purchase.order', string='Vendor Purchase Order')
    vendor_order = fields.Char(string='Vendor Order')
    nfe_tag_ids = fields.Many2many('nfe.xml.tags', 'xml_panel_nfe_tag_rel', 'soc_xml_id', 'tag_id', string='Tags')
    current_company_id = fields.Many2one('res.company', string='Current Company', compute="_compute_company_id")
    team_id = fields.Many2one("crm.team", string="Sales Team", store=True)
    # LAB FORK: without edocs, every panel is an external XML.
    xml_type = fields.Selection([('internal', 'Internal Type'), ('external', 'External Type')], string="Type", default='external', store=True)

    # Cancellation: an NFe is cancelled by a separate procEventoNFe document
    # (tpEvento 110111/110112), stored in the nfe.xml.cancel.event table.
    is_cancelled = fields.Boolean(string="Cancelled", default=False, copy=False,
                                  tracking=True,
                                  help="Set when a cancellation event exists "
                                       "for this NFe access key.")
    cancel_event_ids = fields.One2many('nfe.xml.cancel.event', 'nfe_id',
                                       string="Cancellation Events")
    # Cancellation details surfaced on the document itself (a note has at most
    # one cancellation), stored so they can be shown as columns and filtered.
    cancel_date = fields.Datetime(string="Cancellation Date",
                                  compute='_compute_cancel_info', store=True)
    cancel_protocol = fields.Char(string="Cancellation Protocol",
                                  compute='_compute_cancel_info', store=True)
    cancel_reason = fields.Char(string="Cancellation Reason",
                                compute='_compute_cancel_info', store=True)

    # Direction of the note relative to us, derived from which fiscal side
    # (emitter/recipient) is one of our companies. Filled at import.
    nfe_direction = fields.Selection(
        [
            ('out', 'Outgoing'),
            ('in', 'Incoming'),
            ('internal', 'Internal'),
            ('external', 'External'),
        ], string="Direction", copy=False, tracking=True,
        help="Outgoing: issued by one of our companies (we sold/shipped). "
             "Incoming: addressed to one of our companies (we received). "
             "Internal: between two of our companies. "
             "External: neither side is one of our companies.")

    # Odoo 19: _sql_constraints was replaced by models.Constraint attributes.
    _nfe_key_uniq = models.Constraint(
        'unique ("key")',
        'An NFe XML with this access key already exists!')

    def _compute_company_id(self):
        for nfe in self:
            nfe.current_company_id = nfe.env.company.id

    @api.depends('cancel_event_ids', 'cancel_event_ids.event_date',
                 'cancel_event_ids.protocol', 'cancel_event_ids.reason')
    def _compute_cancel_info(self):
        for nfe in self:
            event = nfe.cancel_event_ids[:1]
            nfe.cancel_date = event.event_date or False
            nfe.cancel_protocol = event.protocol or False
            nfe.cancel_reason = event.reason or False

    @api.model
    def _own_company_cnpjs(self):
        """Digits-only CNPJ set of every registered res.company."""
        partners = self.env['res.company'].sudo().search([]).partner_id
        return {re.sub(r'\D', '', p.vat) for p in partners if p.vat}

    @staticmethod
    def _format_doc(doc):
        """Format a bare CNPJ/CPF the way the panel stores it."""
        if not doc:
            return False
        digits = re.sub(r'\D', '', doc)
        if len(digits) == 14:
            return '{}{}.{}{}{}.{}{}{}/{}{}{}{}-{}{}'.format(*digits)
        if len(digits) == 11:
            return '{}{}{}.{}{}{}.{}{}{}-{}{}'.format(*digits)
        return doc

    def _extract_parties(self):
        """Read emitter/recipient (CNPJ/CPF + name) from the stored XML.

        Cheap: only the two party blocks are read, so this can run at import
        for every note (cancelled or not), independently of the full parse.
        """
        self.ensure_one()
        ns = '{http://www.portalfiscal.inf.br/nfe}'
        try:
            root = self.get_root()
        except Exception:
            return False
        if root is None or root == '':
            return False

        def _party(tag):
            node = root.find('.//%s%s' % (ns, tag))
            if node is None:
                return (False, False)
            doc = node.find('.//%sCNPJ' % ns)
            if doc is None:
                doc = node.find('.//%sCPF' % ns)
            name = node.find('.//%sxNome' % ns)
            return (doc.text if doc is not None else False,
                    name.text if name is not None else False)

        emit_doc, emit_name = _party('emit')
        dest_doc, dest_name = _party('dest')
        return {
            'emit_doc': self._format_doc(emit_doc), 'emit_name': emit_name or False,
            'dest_doc': self._format_doc(dest_doc), 'dest_name': dest_name or False,
        }

    def _match_own_company(self, doc):
        digits = re.sub(r'\D', '', doc or '')
        if not digits:
            return self.env['res.company']
        for comp in self.env['res.company'].sudo().search([]):
            if re.sub(r'\D', '', comp.partner_id.vat or '') == digits:
                return comp
        return self.env['res.company']

    def _find_or_create_partner(self, doc, name, sync_name=True):
        """Find the counterparty by CNPJ/CPF, creating it if it does not exist.

        The NFe is the official source for the razao social keyed by CNPJ, so
        when ``sync_name`` an existing partner's name is refreshed from the XML
        (this heals partners that older logic created with a wrong name).
        ``sync_name`` is turned off for our own companies.
        """
        digits = re.sub(r'\D', '', doc or '')
        if not digits:
            return self.env['res.partner']
        Partner = self.env['res.partner'].sudo()
        partner = Partner.search(['|', ('vat', '=', doc), ('vat', '=', digits)], limit=1)
        if not partner:
            # A partner born from an NFe has a CNPJ/CPF: it is Brazilian by
            # definition. Odoo renders the sale/quotation PDF in the CUSTOMER's
            # language, so leaving the default (en_US) means every document we
            # send a Brazilian bookshop comes out in English.
            partner = Partner.create({
                'name': name or doc,
                'vat': doc,
                'is_company': len(digits) == 14,
                'company_type': 'company' if len(digits) == 14 else 'person',
                'lang': self._br_lang(),
                'country_id': self.env.ref('base.br', raise_if_not_found=False).id
                              if self.env.ref('base.br', raise_if_not_found=False) else False,
            })
        elif sync_name and name and partner.name != name:
            partner.name = name
        return partner

    @api.model
    def _br_lang(self):
        """pt_BR if it is installed; otherwise leave Odoo's default alone."""
        lang = self.env['res.lang'].with_context(active_test=False).search(
            [('code', '=', 'pt_BR')], limit=1)
        return lang.code if lang and lang.active else False

    def identify_parties(self):
        """Fill the business view (our company, client, direction) from the
        fiscal roles. Client is resolved to a res.partner, created if missing.
        """
        own = self._own_company_cnpjs()
        for rec in self:
            parties = rec._extract_parties()
            if not parties:
                continue
            emit_doc, emit_name = parties['emit_doc'], parties['emit_name']
            dest_doc, dest_name = parties['dest_doc'], parties['dest_name']
            emit_ours = bool(emit_doc) and re.sub(r'\D', '', emit_doc) in own
            dest_ours = bool(dest_doc) and re.sub(r'\D', '', dest_doc) in own

            vals = {
                'vendor_cnpj': emit_doc or False, 'vendor_name': emit_name,
                'customer_cnpj': dest_doc or False, 'customer_name': dest_name,
            }
            if emit_ours and not dest_ours:
                vals['nfe_direction'] = 'out'
                vals['company_id'] = rec._match_own_company(emit_doc).id or False
                client = rec._find_or_create_partner(dest_doc, dest_name)
            elif dest_ours and not emit_ours:
                vals['nfe_direction'] = 'in'
                vals['company_id'] = rec._match_own_company(dest_doc).id or False
                client = rec._find_or_create_partner(emit_doc, emit_name)
            elif emit_ours and dest_ours:
                vals['nfe_direction'] = 'internal'
                vals['company_id'] = rec._match_own_company(emit_doc).id or False
                # Client is another of our companies - don't rename it.
                client = rec._find_or_create_partner(dest_doc, dest_name, sync_name=False)
            else:
                vals['nfe_direction'] = 'external'
                client = rec._find_or_create_partner(dest_doc or emit_doc,
                                                     dest_name or emit_name)
            vals['partner_id'] = client.id or False
            rec.write(vals)

    @api.depends('move_ids')
    def _compute_move_count(self):
        for nfe in self:
            nfe.move_count = len(nfe.move_ids)

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices/Bills of %s') % self.display_name,
            'res_model': 'account.move',
            'domain': [('nfe_xml_panel_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'create': False},
        }

    # update the danfe no and danfe value in old data
    # @api.model_cr
    def init(self):
        for rec in self.search([]):
            if not rec.danfe_no:
                if rec.file != '':
                    data = rec.file
                    try:
                        danfe_no = rec.update_danfe_no(data)
                        if danfe_no:
                            self.env.cr.execute("update nfe_xml_panel set danfe_no=%s where id =%s",
                                                (danfe_no, rec.id,))
                        danfe_value = rec.update_danfe_value(data)
                        if danfe_value:
                            self.env.cr.execute("update nfe_xml_panel set danfe_value=%s where id =%s",
                                                (danfe_value, rec.id,))
                    except:
                        pass

    @api.depends('danfe_no')
    def _compute_display_name(self):
        for com in self:
            com.display_name = (com.danfe_no or '') + '- Nfe :' + str(date.today())

    def _get_partner_team_id(self, partner):
        """Odoo 19 removed team_id from res.partner - fall back to the
        default sales team of the partner's salesperson, if any."""
        partner = partner.with_company(self.company_id or self.env.company)
        if 'team_id' in partner._fields:
            return partner.team_id.id
        if partner.user_id:
            return self.env['crm.team']._get_default_team_id(
                user_id=partner.user_id.id)
        return False

    def action_update_team_id(self):
        for nfe in self:
            if not nfe.team_id and nfe.partner_id:
                nfe.team_id = nfe._get_partner_team_id(nfe.partner_id)

    @api.model
    def cron_process_file_content(self, limit=50):
        nfe_rec = self.env['nfe.xml.panel'].search([('status', '=', 'imported')], limit=limit)
        nfe_rec.action_import_xml_file()

    def action_import_xml_file(self):
        for nfe in self.filtered(lambda nfe_rec: nfe_rec.file and nfe_rec.status in ('imported', 'error')):
            try:
                # Isolate each record in its own savepoint: a failure on one XML
                # rolls back only that record and keeps the cursor healthy, so the
                # error handler below can post its message and set status='error'
                # -- importing many at once no longer aborts the whole request.
                with self.env.cr.savepoint():
                    # Party identification (our company / client / direction) is
                    # done at import; re-run here to be safe for older records.
                    nfe.identify_parties()
                    vals = {
                       'danfe_no': nfe.update_danfe_no({}),
                       'danfe_value': nfe.update_danfe_value({}),
                       'file_create_date': nfe.update_file_create_date(),
                       'cfop_id': nfe.update_cfop(),
                       'panel_items': nfe.update_panel_items(),
                       'due_date': nfe.update_due_date(),
                       'shipping_price': nfe.update_shipping_price(),
                       'key': nfe.update_chave_nfe_key(),
                       'purchase_id': nfe.update_purchase_order(),
                       'vendor_order': nfe.update_vendor_order({}),
                       'status': 'valid',
                    }
                    nfe.write(vals)
                    if nfe.partner_id:
                        nfe.team_id = nfe._get_partner_team_id(nfe.partner_id)
            except Exception as e:
                message = "<b>Error to Import XML file</b><br/>%s" % str(e)
                nfe.message_post(body=message)
                nfe.write({'status': 'error'})

    def update_purchase_order(self):
        """Update Purchase Order : """
        po_number = self.env['purchase.order']
        for record in self:
            root = record.sudo().get_root()
            if record.sudo().partner_id:
                po_tag = record.sudo().partner_id.po_tag
                identification_no = record.sudo().partner_id.identification_no
                po_no = ''
                if po_tag:
                    po_para = ''
                    if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                                                   '{http://www.portalfiscal.inf.br/nfe}enviNFe']:
                        po = root.find('.//{http://www.portalfiscal.inf.br/nfe}' + po_tag)
                        if po is not None:
                            po_para = po.text
                            po_sequence = self.env['ir.sequence'].sudo().search(
                                [('code', '=', 'purchase.order'),
                                 ('company_id', 'in', (record.sudo().company_id.id, False))
                                 ])

                            if identification_no and po_sequence:
                                code = po_sequence.prefix
                                po_para = po_para.split(identification_no)
                                po_para = po_para[1] if len(po_para) == 2 else po_para[-1]
                                match = re.findall(code + '[0-9]*', po_para)
                                if match:
                                    po_no = match[0]

                            if not po_no:
                                res = re.sub('/', '', po_para).split()
                                po_no = res[len(res) - 1]
                                if '(' in po_no:
                                    po_list = po_no.split('(')
                                    if po_list:
                                        po_no = po_list[0]

                            purchase_order = self.env['purchase.order'].sudo().search([('name', '=', po_no)])
                            po_number = purchase_order.id
                else:
                    po_number = self.env['purchase.order']
        return po_number

    def update_vendor_order(self, data):
        """Update Vendor Order : """
        vendor_order = ''
        for record in self:
            root = record.get_root()
            if record.sudo().partner_id:
                vendor_tag = record.sudo().partner_id.vendor_tag
                if vendor_tag:
                    vendor_order = ''
                    if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                                                   '{http://www.portalfiscal.inf.br/nfe}enviNFe']:
                        vendor_po = root.find('.//{http://www.portalfiscal.inf.br/nfe}' + vendor_tag)
                        if vendor_po is not None:
                            vendor_order = vendor_po.text
                else:
                    vendor_order = ''
        return vendor_order

    def update_vendor_cnpj(self):
        """to update vendor cnpj on basis of excel file attached:"""
        for record in self:
            root = record.get_root()
            cnpj = ''

            if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                                           '{http://www.portalfiscal.inf.br/nfe}enviNFe']:

                try:
                    dest = root.find('.//{http://www.portalfiscal.inf.br/nfe}emit')
                    if dest is not None:
                        if dest.tag:
                            cnpj_tag = dest.find('.//{http://www.portalfiscal.inf.br/nfe}CNPJ')
                            cpf_tag = dest.find('.//{http://www.portalfiscal.inf.br/nfe}CPF')
                            if cnpj_tag is not None:
                                cnpj = cnpj_tag.text
                            elif cpf_tag is not None:
                                cnpj = cpf_tag.text
                            else:
                                return False
                        else:
                            return False
                    else:
                        return False
                except Exception as e:
                    return False
                if len(cnpj) > 1:
                    if len(cnpj) == 14:
                        cnpj_cpf = '{}{}.{}{}{}.{}{}{}/{}{}{}{}-{}{}'.format(*cnpj)
                    if len(cnpj) == 11:
                        cnpj_cpf = '{}{}{}.{}{}{}.{}{}{}-{}{}'.format(*cnpj)
                    return cnpj_cpf
            return False

    def update_customer_cnpj(self):
        """to update customer cnpj on basis of excel file attached:"""
        for record in self:
            root = record.get_root()
            cnpj = ''

            if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                                           '{http://www.portalfiscal.inf.br/nfe}enviNFe']:

                try:
                    dest = root.find('.//{http://www.portalfiscal.inf.br/nfe}dest')
                    if dest is not None:
                        if dest.tag:
                            cnpj_tag = dest.find('.//{http://www.portalfiscal.inf.br/nfe}CNPJ')
                            cpf_tag = dest.find('.//{http://www.portalfiscal.inf.br/nfe}CPF')
                            if cnpj_tag is not None:
                                cnpj = cnpj_tag.text
                            elif cpf_tag is not None:
                                cnpj = cpf_tag.text
                            else:
                                return False
                        else:
                            return False
                    else:
                        mod = root.find('.//{http://www.portalfiscal.inf.br/nfe}mod')
                        if mod is not None:
                            if mod.text == '65':
                                partner_id = self.env.company.nfe_xml_partner_id
                                cnpj_cpf = partner_id.vat
                                return cnpj_cpf
                            else:
                                return False
                        else:
                            return False
                except Exception as e:
                    return False
                if len(cnpj) > 1:
                    if len(cnpj) == 14:
                        cnpj_cpf = '{}{}.{}{}{}.{}{}{}/{}{}{}{}-{}{}'.format(*cnpj)
                    if len(cnpj) == 11:
                        cnpj_cpf = '{}{}{}.{}{}{}.{}{}{}-{}{}'.format(*cnpj)
                    return cnpj_cpf
            return False

    def update_customer(self):
        """to update customer on basis of excel file attached:"""
        for record in self:
            root = record.get_root()
            cnpj = ''

            if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                                           '{http://www.portalfiscal.inf.br/nfe}enviNFe']:

                dest = root.find('.//{http://www.portalfiscal.inf.br/nfe}dest')
                if dest is not None:
                    if dest.tag:
                        cnpj_tag = dest.find('.//{http://www.portalfiscal.inf.br/nfe}CNPJ')
                        cpf_tag = dest.find('.//{http://www.portalfiscal.inf.br/nfe}CPF')
                        if cnpj_tag is not None:
                            cnpj = cnpj_tag.text
                            is_cnpj_tag = True
                        elif cpf_tag is not None:
                            cnpj = cpf_tag.text
                            is_cnpj_tag = False
                        else:
                            raise UserError("CNPJ/CPF tag does not found in the XML file")
                    else:
                        raise UserError("dest tag does not found in the XML file! It was needed to find CNPJ/CPF")
                else:
                    mod = root.find('.//{http://www.portalfiscal.inf.br/nfe}mod')
                    if mod is not None:
                        if mod.text == '65':
                            partner_id = self.env.company.nfe_xml_partner_id
                            return partner_id.id
                        else:
                            raise UserError("dest tag does not found in the XML file! It was needed to find CNPJ/CPF. Not even your file is '65'")
                    else:
                        raise UserError("dest tag does not found in the XML file! It was needed to find CNPJ/CPF. Not even your file is '65'")

                if len(cnpj) > 1:
                    if len(cnpj) == 14:
                        cnpj_cpf = '{}{}.{}{}{}.{}{}{}/{}{}{}{}-{}{}'.format(*cnpj)
                    if len(cnpj) == 11:
                        cnpj_cpf = '{}{}{}.{}{}{}.{}{}{}-{}{}'.format(*cnpj)
                    partner_id = self.env['res.partner'].with_context(active_test=False).search(
                        ['|', ('vat', '=', cnpj_cpf), ('vat', '=', cnpj)], limit=1)
                    if partner_id:
                        _logger.info('===== NFe XML partner end %s=====', partner_id.id)
                    else:
                        customer_tag = root.find('.//{http://www.portalfiscal.inf.br/nfe}xNome')
                        if customer_tag is None:
                            raise UserError("xName tag (Customer Name) does not found!")
                        else:
                            customer_name = customer_tag.text
                        dest = root.find('.//{http://www.portalfiscal.inf.br/nfe}enderDest')
                        if dest is not None:
                            if dest.tag:
                                cep_tag = dest.find('.//{http://www.portalfiscal.inf.br/nfe}CEP')
                                if cep_tag is not None:
                                    partner_zip = cep_tag.text
                                else:
                                    raise UserError("CEP tag does not found in the XML file")
                            else:
                                raise UserError("enderDest tag does not found in the XML file! It was needed to find CEP")
                        else:
                            raise UserError("enderDest tag does not found in the XML file! It was needed to find CEP")

                        if len(partner_zip) > 1:
                            zip = '{}{}{}{}{}-{}{}{}'.format(*partner_zip)
                        # LAB FORK: no zip.search.mixin address enrichment nor
                        # l10n_br CNPJ/CPF validation available - create the
                        # partner with the data present in the XML only.
                        partner_id = self.env['res.partner'].create({
                            'name': customer_name,
                            'vat': cnpj_cpf,
                            'zip': zip if len(partner_zip) > 1 else '',
                            'country_id': self.env.ref('base.br').id,
                            'is_company': is_cnpj_tag,
                        })
                    return partner_id.id
            return False

    def update_cfop(self):
        """to update partner and lead on basis of excel file attached:"""
        for record in self:
            root = record.get_root()
            cfop = ''
            if root != '':
                try:
                    cfop = root.find('.//{http://www.portalfiscal.inf.br/nfe}CFOP').text
                except Exception as e:
                    return False
                if len(cfop) > 1:
                    CFOP = self.env['nfe.cfop'].sudo()
                    cfop_id = CFOP.search([('code', '=', cfop)], limit=1)
                    if not cfop_id:
                        # A code we have never seen. It used to be dropped on the
                        # floor: cfop_id stayed NULL and the whole note vanished
                        # from the shelf ledger and from the audit, silently (49
                        # notes were sitting in that hole). Create it with NO
                        # shelf effect, so it SHOWS UP in Settings > CFOP Effects
                        # asking to be classified instead of disappearing.
                        cfop_id = CFOP.create({
                            'code': cfop,
                            'name': _('Unclassified CFOP %s (found in an '
                                      'imported NFe)') % cfop,
                        })
                        _logger.warning(
                            "NFe %s: CFOP %s was not in the table. Created with "
                            "no shelf effect -- classify it in Settings > CFOP "
                            "Effects, or it counts for nothing.",
                            record.danfe_no or record.id, cfop)
                    return cfop_id.id
            return False

    def action_preview_meta_danfe_nfe(self):
        docs = self.file
        file_name = re.split('-NFe.xml', self.file_name)[0]

        if not docs and file_name:
            raise UserError(u'Não existe um E-Doc relacionado à esta fatura')

        meta_pdf = self.env['ir.attachment'].search([('file_size', '>', 0),
                                                     ('name', 'like', file_name),
                                                     ('name', 'ilike', '.pdf')], limit=1)
        _logger.info('PDF : id : %s' % meta_pdf)
        pdf_docs = meta_pdf.datas
        if not pdf_docs:
            raise UserError(u'Não existe um E-Doc relacionado à esta fatura')
        # return self._action_preview_nfe(pdf_docs)
        return {
            'name': 'Original Danfe',
            'type': 'ir.actions.act_url',
            'url': "web/content/?model=" + meta_pdf._name + "&id=" + str(
                meta_pdf.id) + "&filename_field=name&field=datas&download=true&filename=" + meta_pdf.name,
            'target': 'self',
        }

    def update_due_date(self):
        """to update due date s on basis of excel file attached:"""
        for record in self:
            root = record.get_root()
            date = ''
            if root != '':
                try:
                    date = root.find('.//{http://www.portalfiscal.inf.br/nfe}dVenc').text
                except Exception as e:
                    return False
                if date:
                    return date
            return False

    def update_chave_nfe_key(self):
        for record in self:
            root = record.get_root()
            key = ''
            if root != '':
                try:
                    key = root.find('.//{http://www.portalfiscal.inf.br/nfe}chNFe').text
                except Exception as e:
                    return False
                if key:
                    return key
            return False

    def update_shipping_price(self):
        """to update shipping price on basis of excel file attached:"""
        for record in self:
            root = record.get_root()
            shipping_price = ''
            if root != '':
                try:
                    shipping_price = root.find('.//{http://www.portalfiscal.inf.br/nfe}vFrete').text
                except Exception as e:
                    return False
                if shipping_price:
                    return float(shipping_price)
            return False

    def update_panel_items(self):
        """to update xml items on basis of excel file attached:"""
        for record in self:
            root = record.get_root()
            items = []
            if root != '':
                try:
                    for child in root.findall('.//{http://www.portalfiscal.inf.br/nfe}det'):
                        _logger.info('================Get XML items==================')  # debug
                        barcode = child.find('.//{http://www.portalfiscal.inf.br/nfe}cProd').text
                        cEAN_barcode = child.find('.//{http://www.portalfiscal.inf.br/nfe}cEAN').text
                        # LAB FORK: 'SEM GTIN' is the NFe literal for "item
                        # without a barcode" - matching/creating products by it
                        # collapsed every no-barcode item into one bogus
                        # product. Match only by real codes (cProd = internal
                        # reference, usually the ISBN).
                        codes = [
                            code for code in (barcode, cEAN_barcode)
                            if code and code.strip().upper() != 'SEM GTIN'
                        ]
                        product_id = self.env['product.product'].search(
                            ['|', ('default_code', 'in', codes),
                             ('barcode', 'in', codes),
                             ('active', 'in', [True, False])], limit=1
                        ) if codes else self.env['product.product']

                        if not product_id and codes:
                            sales_price = child.find('.//{http://www.portalfiscal.inf.br/nfe}vUnCom').text
                            pro_name = child.find('.//{http://www.portalfiscal.inf.br/nfe}xProd').text
                            has_gtin = cEAN_barcode in codes
                            product_id = self.env['product.product'].create({
                                'name': pro_name,
                                'barcode': cEAN_barcode if has_gtin else False,
                                'default_code': cEAN_barcode if has_gtin else codes[0],
                                # Odoo 18+: stockable goods are 'consu' with
                                # is_storable (the 'product' type is gone).
                                'type': 'consu',
                                'is_storable': True,
                                'list_price': sales_price,
                            })

                        _logger.info('1-----------Product------ %s', product_id)  # debug
                        # create lines if no issues in product
                        try:
                            pro_name = child.find('.//{http://www.portalfiscal.inf.br/nfe}xProd').text
                            qty = child.find('.//{http://www.portalfiscal.inf.br/nfe}qCom').text
                            # unit = child.find('.//{http://www.portalfiscal.inf.br/nfe}uCom').text
                            price = child.find('.//{http://www.portalfiscal.inf.br/nfe}vUnCom').text
                            if child.find('.//{http://www.portalfiscal.inf.br/nfe}vDesc') != None:
                                discount_value = child.find('.//{http://www.portalfiscal.inf.br/nfe}vDesc').text
                            else:
                                discount_value = 0.0
                            product_price = child.find('.//{http://www.portalfiscal.inf.br/nfe}vProd').text
                            if qty != 0:
                                discount = float(discount_value) / float(qty)
                                net_price = (float(product_price) - float(discount_value)) / float(qty)
                            else:
                                discount = net_price = 0

                            items.append((0, 0, {'soc_xml_id': record.id or False,
                                                 'ks_product_barcode': product_id.barcode or False,
                                                 'ks_product_id': product_id.id or False,
                                                 'ks_product_name': pro_name or False,
                                                 'ks_product_qty': float(qty) or 0.0,
                                                 'ks_price': float(price) or 0.0,
                                                 'discount_item': float(discount) or 0.0,
                                                 'net_price': float(net_price) or 0.0,
                                                 'ks_total_price': float(price) * float(qty), }))

                            # if child.find('.//{http://www.portalfiscal.inf.br/nfe}vDesc') != None:
                            #     discount = child.find('.//{http://www.portalfiscal.inf.br/nfe}vDesc').text
                            # _logger.info('3-----------discount------ %s', discount)  # debug
                        except Exception as e:
                            logging.info('Bad Request')
                            _logger.info('----- Product Issue ---- %s', e)
                            pass
                except Exception as e:
                    raise UserError("Error to import items: %s" % e)
                    return []
                return [(5, 0)] + items
            return []

    def update_file_create_date(self):
        """to update partner and lead on basis of excel file attached:"""
        for record in self:
            root = record.get_root()
            if root != '':
                try:
                    date = root.find('.//{http://www.portalfiscal.inf.br/nfe}dhEmi').text
                except Exception as e:
                    return False
                if date:
                    return date[0:10]
            return False

    def update_company(self):
        """to update partner and lead on basis of excel file attached:"""
        for record in self:
            root = record.get_root()
            company_cnpj = ''
            if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                                           '{http://www.portalfiscal.inf.br/nfe}enviNFe']:
                try:
                    dest = root.find('.//{http://www.portalfiscal.inf.br/nfe}dest')
                    if dest.tag:
                        company_cnpj = dest.find('.//{http://www.portalfiscal.inf.br/nfe}CNPJ').text
                except Exception as e:
                    return False
                if len(company_cnpj) > 1:
                    company = '{}{}.{}{}{}.{}{}{}/{}{}{}{}-{}{}'.format(*company_cnpj)
                    partner_id = self.env['res.partner'].sudo().search([('vat', '=', company)], limit=1)
                    company_with_cnpj = self.env['res.company'].sudo().search([('partner_id', '=', partner_id.id)],
                                                                              limit=1)
                    # partner = self.env['res.partner'].sudo().search(['|', ('cnpj_cpf', '=', company),
                    #                                                  ('cnpj_cpf', '=', company_cnpj)], limit=1)
                    if company_with_cnpj:
                        # if partner.company_id.id in [self.env.user.company_id.id,
                        #                              self.env.user.company_id.parent_id.id]:
                        _logger.info('===== NFe XML company end %s=====', company_with_cnpj)
                        return company_with_cnpj.id
            return False

    def update_soc_panel_fields(self, data):
        """to update partner and lead on basis of excel file attached:"""
        for record in self:
            root = record.get_root()
            cnpj = ''

            if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                                           '{http://www.portalfiscal.inf.br/nfe}enviNFe']:

                emit = root.find('.//{http://www.portalfiscal.inf.br/nfe}emit')
                if emit is not None:
                    if emit.tag:
                        cnpj_tag = emit.find('.//{http://www.portalfiscal.inf.br/nfe}CNPJ')
                        cpf_tag = emit.find('.//{http://www.portalfiscal.inf.br/nfe}CPF')
                        if cnpj_tag is not None:
                            cnpj = cnpj_tag.text
                            is_cnpj_tag = True
                        elif cpf_tag is not None:
                            cnpj = cpf_tag.text
                            is_cnpj_tag = False
                        else:
                            raise UserError("CNPJ/CPF tag does not found in the XML file")
                    else:
                        raise UserError("emit tag does not found in the XML file! It was needed to find CNPJ/CPF")
                else:
                    raise UserError("emit tag does not found in the XML file! It was needed to find CNPJ/CPF")

                if len(cnpj) > 1:
                    if len(cnpj) == 14:
                        cnpj_cpf = '{}{}.{}{}{}.{}{}{}/{}{}{}{}-{}{}'.format(*cnpj)
                    if len(cnpj) == 11:
                        cnpj_cpf = '{}{}{}.{}{}{}.{}{}{}-{}{}'.format(*cnpj)
                    partner_id = self.env['res.partner'].with_context(active_test=False).search(
                        ['|', ('vat', '=', cnpj_cpf), ('vat', '=', cnpj)], limit=1)
                    if partner_id:
                        _logger.info('===== NFe XML partner end %s=====', partner_id.id)
                    else:
                        partner_tag = root.find('.//{http://www.portalfiscal.inf.br/nfe}xFant')
                        if partner_tag is None:
                            raise UserError("xFant tag (Partner Name) does not found!")
                        else:
                            partner_name = partner_tag.text
                        emit = root.find('.//{http://www.portalfiscal.inf.br/nfe}enderEmit')

                        if emit is not None:
                            if emit.tag:
                                cep_tag = emit.find('.//{http://www.portalfiscal.inf.br/nfe}CEP')
                                if cep_tag is not None:
                                    partner_zip = cep_tag.text
                                else:
                                    raise UserError("CEP tag does not found in the XML file")
                            else:
                                raise UserError("enderEmit tag does not found in the XML file! It was needed to find CEP")
                        else:
                            raise UserError("enderEmit tag does not found in the XML file! It was needed to find CEP")

                        if len(partner_zip) > 1:
                            zip = '{}{}{}{}{}-{}{}{}'.format(*partner_zip)
                        # LAB FORK: no zip.search.mixin address enrichment nor
                        # l10n_br CNPJ/CPF validation available - create the
                        # partner with the data present in the XML only.
                        partner_id = self.env['res.partner'].create({
                            'name': partner_name,
                            'vat': cnpj_cpf,
                            'zip': zip if len(partner_zip) > 1 else '',
                            'country_id': self.env.ref('base.br').id,
                            'is_company': is_cnpj_tag,
                        })
                    return partner_id.id
            return False

    def update_danfe_no(self, data):
        # Update Danfe no.:
        for record in self:
            root = record.get_root()

            if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                                           '{http://www.portalfiscal.inf.br/nfe}enviNFe']:
                danfe_no = ''
                serie_no = ''

                danfe = root.find('.//{http://www.portalfiscal.inf.br/nfe}nNF')
                serie = root.find('.//{http://www.portalfiscal.inf.br/nfe}serie')
                if danfe is not None:
                    danfe_no = danfe.text
                    x = len(danfe_no)
                    zeroes = '0' * (9 - x)
                    danfe_no = zeroes + danfe_no
                    danfe_no = '{}{}{}.{}{}{}.{}{}{}'.format(*danfe_no)
                if serie is not None:
                    serie = serie.text
                return danfe_no

    def update_danfe_value(self, data):
        # Update Danfe Value:
        for record in self:
            root = record.get_root()
            danfe_value = 0.0

            if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                                           '{http://www.portalfiscal.inf.br/nfe}enviNFe']:
                for child in root.findall('.//{http://www.portalfiscal.inf.br/nfe}total'):
                    total = child.find('.//{http://www.portalfiscal.inf.br/nfe}vNF')
                    if total is not None:
                        danfe_value = float(total.text)
            return danfe_value

    def get_root(self):
        """Parse the stored XML and return its root element ('' if empty).

        LAB FORK / Odoo 19: parse in memory. The original wrote the binary
        to a NamedTemporaryFile and ET.parse()d it WITHOUT flushing - any
        XML smaller than the 8KB IO buffer produced an empty file and a
        'no element found' error.
        """
        self.ensure_one()
        if not self.file:
            return ''
        return ET.fromstring(base64.b64decode(self.file))

    @api.model
    def is_valid_xml_and_nfe_key(self, xml_file):
        root = ''
        try:
            root = ET.fromstring(xml_file)

            if root != '' and root.tag in ['{http://www.portalfiscal.inf.br/nfe}nfeProc',
                           '{http://www.portalfiscal.inf.br/nfe}enviNFe']:
                try:
                    protNFe = root.find('.//{http://www.portalfiscal.inf.br/nfe}protNFe')
                    if protNFe.tag:
                        xml_number = protNFe.find('.//{http://www.portalfiscal.inf.br/nfe}chNFe').text
                except Exception as e:
                    xml_number = ''

                if xml_number:
                    xml_nfe_exists = self.env['nfe.xml.panel'].sudo().search([('key', '=', xml_number)])
                    if not xml_nfe_exists:
                        return xml_number
            return False
        except Exception as e:
            return False

    @api.model
    def _company_from_xml(self, xml_file):
        """The res.company an NFe belongs to, matched by CNPJ (emit, then dest).

        A note belongs to whichever of our companies issued or received it -
        never to "whatever company the caller happened to pass in". With more
        than one company (or more than one Olist account) feeding the same
        database, trusting the caller is how notes end up filed under the wrong
        company; the XML itself is the only trustworthy source.

        Returns an empty recordset when neither side is one of our companies.
        """
        ns = '{http://www.portalfiscal.inf.br/nfe}'
        try:
            root = ET.fromstring(xml_file)
        except Exception:
            return self.env['res.company']
        for tag in ('emit', 'dest'):
            node = root.find('.//%s%s' % (ns, tag))
            if node is None:
                continue
            doc = node.find('.//%sCNPJ' % ns)
            if doc is None or not doc.text:
                continue
            company = self._match_own_company(doc.text)
            if company:
                return company
        return self.env['res.company']

    @api.model
    def _ingest_xml(self, xml_file, file_name, company=False, source='manual',
                    extra_vals=None):
        """Create a panel from raw NFe XML bytes. THE entry point for adapters.

        Every source (manual ZIP upload, attachment cron, Olist API) funnels
        through here, so they all get the same validation and the same dedupe:
        ``is_valid_xml_and_nfe_key`` returns False both for non-NFe XML and for
        a chNFe that is already imported, which is what makes re-running any
        adapter safe.

        ``company`` defaults to the one derived from the XML itself
        (:meth:`_company_from_xml`). Returns the panel, or False if skipped.
        """
        key = self.is_valid_xml_and_nfe_key(xml_file)
        if not key:
            return False
        if company is False:
            company = self._company_from_xml(xml_file)
        vals = {
            'file': base64.encodebytes(xml_file),
            'file_name': file_name,
            'company_id': company.id if company else False,
            'key': key,
            'status': 'imported',
            'source': source,
        }
        vals.update(extra_vals or {})
        panel = self.create(vals)
        # Cheap, and works even for notes that are never fully processed.
        panel.identify_parties()
        return panel

    # tpEvento values that cancel an existing NFe.
    # 110111 = Cancelamento, 110112 = Cancelamento por Substituicao.
    # (110110 = Carta de Correcao does NOT cancel and is ignored.)
    NFE_CANCEL_EVENTS = ('110111', '110112')

    @api.model
    def parse_nfe_event(self, xml_file):
        """Return the event data of a ``procEventoNFe`` XML, else ``False``.

        Event XMLs (cancellations, correction letters) have no emit/dest/items,
        so ``is_valid_xml_and_nfe_key`` rejects them and they used to be dropped
        silently. This lets the import route them by their ``tpEvento``.
        """
        ns = '{http://www.portalfiscal.inf.br/nfe}'
        try:
            root = ET.fromstring(xml_file)
        except Exception:
            return False
        if root is None or not root.tag.endswith('procEventoNFe'):
            return False
        inf_evento = root.find('.//%sinfEvento' % ns)
        if inf_evento is None:
            return False

        def _text(local_name):
            el = inf_evento.find('.//%s%s' % (ns, local_name))
            return el.text if el is not None else False

        return {
            'ch_nfe': _text('chNFe'),
            'tp_evento': _text('tpEvento'),
            'dh_evento': _text('dhEvento'),
            'n_prot': _text('nProt'),
            'x_just': _text('xJust'),
            'desc_evento': _text('descEvento'),
        }

    @api.model
    def register_cancellation_event(self, xml_file, file_name=False, company_id=False):
        """Store a cancellation event and flag the NFe it cancels.

        Parses ``xml_file`` as a ``procEventoNFe``; if it is a cancellation
        (see :attr:`NFE_CANCEL_EVENTS`) the event is upserted into
        ``nfe.xml.cancel.event`` (keyed by ``chNFe``) and the matching
        ``nfe.xml.panel`` record, if any, is flagged ``is_cancelled``.
        Returns the ``nfe.xml.cancel.event`` record, or ``False`` when the XML
        is not a cancellation.
        """
        info = self.parse_nfe_event(xml_file)
        if not info or info.get('tp_evento') not in self.NFE_CANCEL_EVENTS:
            return False
        ch_nfe = info.get('ch_nfe')
        if not ch_nfe:
            return False

        Event = self.env['nfe.xml.cancel.event'].sudo()
        nfe = self.sudo().search([('key', '=', ch_nfe)], limit=1)
        vals = {
            'key': ch_nfe,
            'nfe_id': nfe.id or False,
            'tp_evento': info.get('tp_evento') or False,
            'protocol': info.get('n_prot') or False,
            'reason': info.get('x_just') or False,
            'desc_evento': info.get('desc_evento') or False,
            'file': base64.b64encode(xml_file),
            'file_name': file_name or (ch_nfe + '-can.xml'),
            'company_id': company_id or (nfe.company_id.id if nfe else False),
        }
        dh_evento = info.get('dh_evento')
        if dh_evento:
            # dhEvento is ISO-8601 with timezone, e.g. 2023-02-17T16:02:44-03:00
            vals['event_date'] = dh_evento[:19].replace('T', ' ')

        event = Event.search([('key', '=', ch_nfe)], limit=1)
        if event:
            event.write(vals)
        else:
            event = Event.create(vals)

        if nfe and nfe.status != 'cancelled':
            nfe.write({'is_cancelled': True, 'status': 'cancelled'})
            nfe.message_post(body=_('NFe cancelled (protocol %s). Reason: %s') % (
                info.get('n_prot') or '-', info.get('x_just') or '-'))
        return event

    # LAB FORK / Odoo 19: compare_vendor_bill() removed - it depended on the
    # 'nfe.xml.wizard' model that never existed in this fork, so its cron
    # only produced "Exception in comparing XML" chatter noise.

    def action_download_nfe_xml_attachment(self):
        tab_id = []
        for attachment in self:
            # attachment_ids = self.env['ir.attachment'].search([('res_id', '=', attachment.id),
            #                                                    ('description', '=', 'Auto_Danfe_Xml'),
            #                                                    ('res_model', '=', 'account.invoice')],
            #                                                   limit=1)
            tab_id.append(attachment.id)
        url = '/web/binary/liber_nfe_xml/download_document?tab_id=%s' % tab_id
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_download_nfe_danfe_attachment(self):
        tab_id = []
        for attachment in self:
            docs = attachment.file
            file_name = re.split('-NFe.xml', attachment.file_name)[0]

            if docs and file_name:
                meta_pdf = self.env['ir.attachment'].search([('file_size', '>', 0),
                                                             ('name', 'like', file_name),
                                                             ('name', 'ilike', '.pdf')], limit=1)
                tab_id.append(meta_pdf.id)
        url = '/web/binary/nfe_danfe/download_document?tab_id=%s' % tab_id
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    # '''Not using now'''
    # def nfe_xml_update_items_cron(self):
    #     records = self.env['nfe.xml.panel'].search([])
    #     for rec in records:
    #         try:
    #             if rec.file and not rec.panel_items:
    #                 rec.sudo().write({'panel_items': rec.update_panel_items(),
    #                                    'due_date': rec.update_due_date(),
    #                                    'shipping_price': rec.update_shipping_price(),
    #                                    })
    #                 rec.env.cr.commit()
    #         except Exception as e:
    #             _logger.error(e)

class SocXmlItems(models.Model):
    _name = 'nfe.xml.items'
    _description = "NFe XML Items"
    _rec_name = 'soc_xml_id'

    # name = fields.Char("Name", default='XML Items',
    #                    copy=False, readonly=True, index='True', track_visibility='always')
    soc_xml_id = fields.Many2one('nfe.xml.panel', string='XML Reference', ondelete="cascade")
    ks_product_id = fields.Many2one('product.product', string='Product', readonly=True)
    ks_product_name = fields.Char(string='Product Name', readonly=True)
    ks_product_qty = fields.Float(string='Quantity', default=0.0)
    ks_price = fields.Float(string='Price', default=0.0)
    ks_total_price = fields.Float(string='Total Price', compute='compute_xml_items_total_price', store=True)
    ks_product_barcode = fields.Char(string='Barcode', readonly=True)
    ks_due_date = fields.Date(string='XML Due Date', related="soc_xml_id.due_date", store=True)
    ks_xml_date = fields.Date(string='XML Date', related="soc_xml_id.file_create_date", store=True)
    ks_cfop_id = fields.Many2one(string='CFOP', related="soc_xml_id.cfop_id", store=True)
    ks_purchase_id = fields.Many2one(string='Purchase Order', related="soc_xml_id.po_id", store=True)
    ks_partner_id = fields.Many2one(string='Partner', related="soc_xml_id.partner_id", store=True)
    company_id = fields.Many2one(related="soc_xml_id.company_id", store=True)
    team_id = fields.Many2one(related="soc_xml_id.team_id", store=True)
    discount_item = fields.Float(string="Discount")
    net_price = fields.Float(string='Net Price')
    vendor_id = fields.Many2one(string='Sender Name', related="soc_xml_id.vendor_id", store=True)
    customer_id = fields.Many2one(string='Receiver Name', related="soc_xml_id.customer_id", store=True)
    nfe_tag_ids = fields.Many2many('nfe.xml.tags', 'xml_panel_item_nfe_tag_rel', 'soc_xml_item_id', 'tag_id', related="soc_xml_id.nfe_tag_ids", string="NFe Tags", store=True)
    xml_type = fields.Selection(related="soc_xml_id.xml_type", store=True)


    @api.depends()
    def compute_xml_items_total_price(self):
        for rec in self:
            rec.ks_total_price = rec.ks_price * rec.ks_product_qty


class SocXmlTags(models.Model):
    _name = "nfe.xml.tags"
    _description = "NFe XML Tags"

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char('Tag Name', required=True, translate=True)
    color = fields.Integer('Color', default=_get_default_color)

    _name_uniq = models.Constraint(
        'unique (name)', "Tag name already exists !")
