# -*- coding: utf-8 -*-
"""Invoice/bill creation from NFe XML panels.

LAB FORK / Odoo 19: the SSOC/RSO/SO/PO order flows were removed - they
depended on models that never existed in this fork (``soc.type``,
``nfe.xml.wizard``, ``order_type`` fields) and were dead code since v15.
What remains is the XML -> account.move path, now linked through the NFe
access key (``account.move.nfe_key``) instead of raw database ids.
"""
import logging
import re
import xml.etree.ElementTree as ET

from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

NFE_NS = '{http://www.portalfiscal.inf.br/nfe}'


class NfeXmlPanel(models.Model):
    _inherit = 'nfe.xml.panel'

    def _find_existing_move(self, move_type):
        """Return a non-cancelled move already created from this NFe key."""
        self.ensure_one()
        if not self.key:
            return self.env['account.move']
        return self.env['account.move'].search(
            [('nfe_key', '=', self.key),
             ('move_type', '=', move_type),
             ('state', '!=', 'cancel')], limit=1)

    def _prepare_move_lines_from_xml(self, root):
        """Parse the NFe ``det`` nodes into invoice line commands."""
        invoice_lines = []
        issue_product_tmpl_ids = []
        for child in root.findall('.//%sdet' % NFE_NS):
            discount = 0.0
            barcode = child.find('.//%scProd' % NFE_NS).text
            cean_barcode = child.find('.//%scEAN' % NFE_NS).text
            # LAB FORK: ignore the 'SEM GTIN' literal and match by any real
            # code (OR, like the panel import) - an AND domain would miss
            # products without a barcode.
            codes = [
                code for code in (barcode, cean_barcode)
                if code and code.strip().upper() != 'SEM GTIN'
            ]
            product_id = self.env['product.product'].search(
                ['|', ('default_code', 'in', codes),
                 ('barcode', 'in', codes),
                 ('active', '=', True)], limit=1
            ) if codes else self.env['product.product']
            if not product_id:
                _logger.info('NFe XML %s: product not found for codes %s',
                             self.id, codes)
                continue
            try:
                qty = child.find('.//%sqCom' % NFE_NS).text
                price = child.find('.//%svUnCom' % NFE_NS).text
                if child.find('.//%svDesc' % NFE_NS) is not None:
                    discount = child.find('.//%svDesc' % NFE_NS).text
                account_id = (
                    product_id.property_account_income_id.id
                    or product_id.categ_id.property_account_income_categ_id.id)
                vals = {
                    'product_id': product_id.id,
                    'name': product_id.name,
                    'quantity': float(qty),
                    'product_uom_id': product_id.uom_id.id,
                    'price_unit': float(price),
                    'discount': ((float(discount) * 100) / (
                            float(qty) * float(price))) if discount else 0,
                }
                # only force the account when the product defines one -
                # an explicit False would suppress the default computed
                # from the journal and violate the accountable-line check
                if account_id:
                    vals['account_id'] = account_id
                invoice_lines.append((0, 0, vals))
            except Exception as e:
                _logger.info('NFe XML %s: issue on line for %s: %s',
                             self.id, product_id.display_name, e)
                issue_product_tmpl_ids.append(product_id.product_tmpl_id.id)
        return invoice_lines, issue_product_tmpl_ids

    def _check_xml_partner(self, root):
        """Ensure the record's partner is actually a party on the NFe.

        LAB FORK: partner_id is the counterparty (client), derived by
        identify_parties from the correct emit/dest node according to the
        NFe direction. The legacy check read the *first* <CNPJ> in the
        document - always the emitter - and so wrongly rejected every
        outgoing note (partner = recipient, not emitter). Accept the
        partner when its VAT matches either party (emitter or recipient).
        """
        self.ensure_one()
        if not self.partner_id:
            return

        def _party_doc(tag):
            node = root.find('.//%s%s' % (NFE_NS, tag))
            if node is None:
                return ''
            doc = node.find('.//%sCNPJ' % NFE_NS)
            if doc is None:
                doc = node.find('.//%sCPF' % NFE_NS)
            return re.sub(r'\D', '', doc.text) if (doc is not None and doc.text) else ''

        party_docs = {_party_doc('emit'), _party_doc('dest')} - {''}
        partner_vat = re.sub(r'\D', '', self.partner_id.vat or '')
        if party_docs and partner_vat and partner_vat not in party_docs:
            raise UserError(_(
                "The partner on this record (%s) is not a party on the NFe "
                "XML.") % self.partner_id.display_name)

    def _post_move_creation_messages(self, move, issue_product_tmpl_ids):
        self.ensure_one()
        if issue_product_tmpl_ids:
            msg = _("Issues with products : ") + "<br/>"
            pro_ids = self.env['product.template'].browse(
                set(issue_product_tmpl_ids))
            for pro in pro_ids:
                msg += ('<a href=# data-oe-model=product.template '
                        'data-oe-id=%d>%s</a> <br/>') % (pro.id, pro.barcode)
            self.message_post(body=msg)
            move.message_post(body=msg)
        move.message_post(body=_("Created from NFe XML file"))
        self.message_post(body=_(
            "%(type)s has been created from this XML file : "
            "<a href=# data-oe-model=account.move data-oe-id=%(id)d>"
            "%(name)s</a>",
            type=move.move_type == 'in_invoice' and _('Bill') or _('Invoice'),
            id=move.id, name=move.ref or move.display_name))

    def bill_import_ail(self):
        """Create Vendor Bills from the XML files (batch-safe, like the
        invoice flow)."""
        created = self.env['account.move']
        skipped = 0
        for record in self:
            if record.is_cancelled or record.invoice_id:
                skipped += 1
                continue
            try:
                # savepoint: a DB error on one record must not abort the
                # whole batch transaction (message_post would break too)
                with self.env.cr.savepoint():
                    bill = record._bill_import_one()
            except Exception as e:
                _logger.info('Issue on Bill creation: %s', e)
                record.message_post(
                    body=_('Issue while creating the Bill: %s') % e)
                skipped += 1
                continue
            if bill:
                created |= bill
            else:
                skipped += 1
        return self._moves_created_action(created, skipped, 'in_invoice')

    def _bill_import_one(self):
        self.ensure_one()
        existing = self._find_existing_move('in_invoice')
        if existing:
            self.message_post(body=_(
                "A bill for this NFe key already exists: "
                "<a href=# data-oe-model=account.move data-oe-id=%d>%s</a>")
                % (existing.id, existing.display_name))
            self.invoice_id = existing.id
            return self.env['account.move']

        root = self.get_root()
        self._check_xml_partner(root)
        invoice_lines, issues = self._prepare_move_lines_from_xml(root)

        bill = self.env['account.move'].create({
            'partner_id': self.partner_id.id,
            'invoice_origin': self.file_name or "Nfe-XML Bill",
            'ref': self.danfe_no or "Nfe-XML Bill",
            'move_type': 'in_invoice',
            'company_id': (self.company_id.id
                           or self.env.company.id),
            'invoice_date': self.file_create_date,
            'invoice_date_due': self.due_date,
            'invoice_line_ids': invoice_lines,
            # Business-key link: the NFe access key ties the move to this
            # panel; nfe_xml_panel_id is computed from it.
            'nfe_key': self.key or False,
        })
        _logger.info('NFe XML %s: bill created %s', self.id, bill)
        if not self.key:
            # legacy XML without access key: keep the direct link
            bill.nfe_xml_panel_id = self.id
        self._post_move_creation_messages(bill, issues)
        self.invoice_id = bill.id
        return bill

    def invoice_import_ail(self):
        """Create Customer Invoices from the XML files (LAB FORK:
        batch-safe).

        Every selected record is handled: cancelled notes and notes already
        linked to a move are skipped, per-record failures land on the
        record's chatter, and the action ends by opening the invoices it
        created.
        """
        created = self.env['account.move']
        skipped = 0
        for record in self:
            if record.is_cancelled or record.invoice_id:
                skipped += 1
                continue
            try:
                with self.env.cr.savepoint():
                    invoice = record._invoice_import_one()
            except Exception as e:
                _logger.info('Issue on Invoice creation: %s', e)
                record.message_post(
                    body=_('Issue while creating the Invoice: %s') % e)
                skipped += 1
                continue
            if invoice:
                created |= invoice
            else:
                skipped += 1
        return self._moves_created_action(created, skipped, 'out_invoice')

    def _invoice_import_one(self):
        """Create one customer invoice from this panel's XML, dated on the
        XML emission date and linked through the NFe access key."""
        self.ensure_one()
        existing = self._find_existing_move('out_invoice')
        if existing:
            self.message_post(body=_(
                "An invoice for this NFe key already exists: "
                "<a href=# data-oe-model=account.move data-oe-id=%d>%s</a>")
                % (existing.id, existing.display_name))
            self.invoice_id = existing.id
            return self.env['account.move']

        root = self.get_root()
        self._check_xml_partner(root)
        invoice_lines, issues = self._prepare_move_lines_from_xml(root)

        invoice = self.env['account.move'].create({
            'partner_id': self.partner_id.id,
            'invoice_origin': self.file_name or "Nfe-XML Invoice",
            # LAB FORK: date the invoice on the XML emission date and keep
            # the DANFE number as the reference.
            'invoice_date': self.file_create_date,
            'ref': self.danfe_no or "Nfe-XML Invoice",
            'move_type': 'out_invoice',
            'company_id': (self.company_id.id
                           or self.env.company.id),
            'invoice_line_ids': invoice_lines,
            'nfe_key': self.key or False,
        })
        _logger.info('NFe XML %s: invoice created %s', self.id, invoice)
        if not self.key:
            invoice.nfe_xml_panel_id = self.id
        self._post_move_creation_messages(invoice, issues)
        self.invoice_id = invoice.id
        return invoice

    def _moves_created_action(self, created, skipped, move_type):
        if not created:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Create Invoice'),
                    'message': _('No invoice created - %s record(s) skipped '
                                 '(already processed or with issues; see '
                                 'their chatter).') % skipped,
                    'type': 'warning',
                    'sticky': False,
                },
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices from NFe XML'),
            'res_model': 'account.move',
            'domain': [('id', 'in', created.ids)],
            'view_mode': 'list,form',
            'context': {'create': False, 'default_move_type': move_type},
        }
