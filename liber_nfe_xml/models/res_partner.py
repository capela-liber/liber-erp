# -*- coding: utf-8 -*-

import io
import re
from odoo import models, fields, api, _
import base64
import datetime
import logging

_logger = logging.getLogger(__name__)

CPF_DIGITS = 11
CNPJ_DIGITS = 14


class NFeResPartner(models.Model):
    _inherit = 'res.partner'

    identification_no = fields.Char('Identification No.')
    po_tag = fields.Char('PO XML tag')
    vendor_tag = fields.Char('Vendor Order XML tag')
    vat_digits = fields.Char(
        string="CNPJ/CPF (digits only)",
        compute='_compute_vat_digits', store=True, index=True, copy=False,
        help="The document with every separator stripped. The NFe carries it "
             "as bare digits while the register almost always holds it "
             "punctuated, so matching the two as plain strings never hits: "
             "this is the field the XML import looks the counterparty up by.")

    @api.depends('vat')
    def _compute_vat_digits(self):
        for partner in self:
            partner.vat_digits = self._vat_digits(partner.vat) or False

    @api.model
    def _vat_digits(self, doc):
        """The document reduced to its digits, or ''.

        Punctuation in the register is not merely '.' '/' '-': this base holds
        documents typed with a SOFT HYPHEN (U+00AD), invisible on screen, and
        with the dots in the wrong places ('00.300662/0001-87'). Anything that
        is not a digit goes.
        """
        return re.sub(r'\D', '', doc or '')

    @api.model
    def _vat_formatted(self, doc):
        """The document punctuated the way it is written in Brazil.

        A register where the same CNPJ appears as '43791310000199',
        '43.791.310/0001-99' and '43791310/0001-99' is a register nobody can
        read a column of. Matching never depended on the punctuation
        (``vat_digits`` exists for that), but reading does.

        A vat carrying LETTERS is left exactly as typed: a French 'FR123...'
        happens to reduce to eleven digits, and formatting it as a CPF would
        turn a foreign supplier's document into a Brazilian one. Anything that
        is neither eleven nor fourteen digits is also left alone -- this base
        holds documents with 5, 8, 12 and 13 digits, and inventing separators
        for them would only hide that they are broken.
        """
        if not doc or re.search(r'[A-Za-z]', doc):
            return doc
        digits = self._vat_digits(doc)
        if len(digits) == CNPJ_DIGITS:
            return '%s.%s.%s/%s-%s' % (
                digits[:2], digits[2:5], digits[5:8], digits[8:12], digits[12:])
        if len(digits) == CPF_DIGITS:
            return '%s.%s.%s-%s' % (
                digits[:3], digits[3:6], digits[6:9], digits[9:])
        return doc

    @api.model
    def _vat_is_valid_br(self, doc):
        """Whether the check digits of a CPF or CNPJ add up.

        Odoo already ships this in ``base_vat`` (``check_vat_br``), and the
        first instinct was to install it. Two reasons not to, both measured on
        the 2026 merge:

        * it would UNDO the mask. ``base_vat`` reformats through
          ``stdnum.br.vat``, which resolves to ``stdnum.br.cnpj.compact`` and
          strips every separator: '171.037.078-55' would be rewritten as
          '17103707855' on every save;
        * it validates as a hard constraint, and this base still holds 21
          documents that do not add up out of 14,745.

        So the arithmetic lives here, where it can be a warning instead of a
        wall. It is deliberately NOT wired into the company/person rules: a
        CNPJ with a typo is still recognisably a CNPJ, and a register that
        refuses to file it correctly helps nobody.

        Returns True for anything that is not an eleven or fourteen digit
        document -- foreign vats and the ten broken ones are not this
        function's to judge. The letter check is not decoration: 'FR12345678901'
        reduces to eleven digits and would be failed as a bad CPF.
        """
        if doc and re.search(r'[A-Za-z]', doc):
            return True
        digits = self._vat_digits(doc)
        if len(digits) == CPF_DIGITS:
            if digits == digits[0] * CPF_DIGITS:
                return False
            for size in (9, 10):
                total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
                if int(digits[size]) != (total * 10) % 11 % 10:
                    return False
            return True
        if len(digits) == CNPJ_DIGITS:
            if digits.startswith('000000000000'):
                return False
            values = [int(c) for c in digits[:12]]
            for weights in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
                            [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
                check = (11 - sum(w * v for w, v in zip(weights, values))) % 11 % 10
                values.append(check)
            return digits[-2:] == '%s%s' % (values[12], values[13])
        return True

    def _document_says_company(self):
        """The records whose CNPJ means they are a company, not a person.

        A CNPJ is issued to a legal entity: a contact holding one is a company,
        and the register saying otherwise is a mistake -- 26 of them in the
        2026 merge, from LIVRARIA DA CENTRAL to Paulinas.

        ONE DIRECTION ONLY. The mirror rule (CPF means a person) would be a
        disaster here: 36 real companies carry a CPF in ``vat``, among them
        Edlab Press and n-1 themselves. There the document is wrong, not the
        record, and demoting them to natural persons would corrupt the file.

        The exception is a child whose document is its parent's. ``vat`` is a
        synced commercial field: Odoo pushes it down onto every contact of a
        company (and back up if one is edited), so the CNPJ on 'Alexandre' is
        the Panaceia's, not his. Promoting him would invent a company that does
        not exist. Four such contacts in this base, and 84 carrying the
        parent's document overall.
        """
        promote = self.browse()
        for partner in self:
            if partner.is_company:
                continue
            digits = self._vat_digits(partner.vat)
            if len(digits) != CNPJ_DIGITS:
                continue
            if partner.parent_id and self._vat_digits(partner.parent_id.vat) == digits:
                continue
            promote |= partner
        return promote

    def _document_says_person(self):
        """The records whose CPF means they are a natural person.

        The mirror of the rule above, and it has to be far more timid, because
        the Contacts app hands every new contact ``default_is_company=True``:
        typing a CPF into a fresh record leaves a person filed as a company,
        which is where this started.

        NEW RECORDS ONLY -- the caller enforces it. Among the ones already
        saved in this base, 37 companies hold a CPF in ``vat``, 28 of them with
        contacts hanging underneath and 21 with sale orders: Edlab Press, n-1,
        Livraria da Vila. There the document is wrong and the record is right,
        and demoting a publisher to a natural person because someone reopened
        its form would be the worst thing this module could do.

        The child guard stays anyway: a record with contacts under it is not a
        natural person, whatever its document says.
        """
        demote = self.browse()
        for partner in self:
            if not partner.is_company or partner.child_ids:
                continue
            if len(self._vat_digits(partner.vat)) != CPF_DIGITS:
                continue
            demote |= partner
        return demote

    @api.onchange('vat')
    def _onchange_vat_document_br(self):
        """On screen the document punctuates itself and a CNPJ ticks 'Company'.

        Doing it here as well as on write is not redundant: seeing the radio
        move while typing is what teaches the rule. Whoever disagrees can move
        it back before saving, and the save will respect that.
        """
        if not self.vat:
            return
        self.vat = self._vat_formatted(self.vat)
        if self._document_says_company():
            self.is_company = True
        elif not self._origin and self._document_says_person():
            # `_origin` is empty while the record has never been saved. On an
            # existing form the radio is left alone: reopening n-1 and touching
            # its document must not turn the publisher into a person.
            self.is_company = False

        # A warning, never a refusal. Whoever is copying a document from a
        # badly printed invoice needs to be told it does not add up; whoever is
        # migrating a register that already holds 21 broken ones still has to
        # be able to save the record.
        digits = self._vat_digits(self.vat)
        if len(digits) not in (CPF_DIGITS, CNPJ_DIGITS):
            if not re.search(r'[A-Za-z]', self.vat or ''):
                return {'warning': {
                    'title': _("Document out of shape"),
                    'message': _(
                        "%(doc)s has %(n)s digits: it is neither a CPF (11) "
                        "nor a CNPJ (14).",
                        doc=self.vat, n=len(digits)),
                }}
        elif not self._vat_is_valid_br(self.vat):
            return {'warning': {
                'title': _("Invalid CPF/CNPJ"),
                'message': _(
                    "The check digits of %(doc)s do not add up. The contact "
                    "can still be saved, but do check the document.",
                    doc=self.vat),
            }}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('vat'):
                vals['vat'] = self._vat_formatted(vals['vat'])
        partners = super().create(vals_list)
        promote = partners._document_says_company()
        if promote:
            promote.is_company = True
        # A record being born is the one moment the CPF may speak too: the
        # Contacts app defaults every new contact to Company, so without this a
        # spreadsheet of readers imports as thirteen thousand companies.
        demote = (partners - promote)._document_says_person()
        if demote:
            demote.is_company = False
        return partners

    def write(self, vals):
        if vals.get('vat'):
            vals = dict(vals, vat=self._vat_formatted(vals['vat']))
        res = super().write(vals)
        # Only when the document (or the parent it may belong to) is the thing
        # being changed, and never against an explicit choice made in the same
        # write: someone ticking 'Individual' by hand is answering the rule,
        # not tripping over it. On create there is no such choice to respect --
        # a spreadsheet import carries whatever the spreadsheet had, and the
        # CNPJ is the more reliable of the two.
        muda_documento = 'vat' in vals or 'parent_id' in vals
        escolha_explicita = 'is_company' in vals or 'company_type' in vals
        if muda_documento and not escolha_explicita:
            promote = self._document_says_company()
            if promote:
                promote.is_company = True
        return res

    @api.model
    def _find_by_document(self, doc):
        """The partner holding ``doc``, whatever punctuation either side uses.

        A document identifies a legal entity, and Odoo copies a company's vat
        down onto its child contacts - in this base the Edlab CNPJ sits on 21
        people as well as on the company. So a top-level record always wins:
        matching a note against "Jorge Sallum" instead of "Edlab Press" would
        file it under the person who happens to be a contact there.

        Among equals the oldest wins, so a base that already carries real
        duplicates keeps answering with the same record instead of drifting
        between them from one note to the next.

        Runs with the caller's own rights and context on purpose - some call
        sites need ``sudo()``, others need ``active_test=False``, and the
        helper must not decide that for them.
        """
        digits = self._vat_digits(doc)
        if not digits:
            return self.browse()
        matches = self.search([('vat_digits', '=', digits)], order='id')
        if not matches:
            return self.browse()
        top_level = matches.filtered(lambda p: not p.parent_id)
        return (top_level or matches.commercial_partner_id or matches)[:1]

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
