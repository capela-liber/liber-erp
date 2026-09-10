# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models

CNPJ_ROOT_DIGITS = 8


class PartnerGroup(models.Model):
    _name = 'liber.partner.group'
    _description = 'Commercial Group (bookstore network)'
    _order = 'name'

    name = fields.Char(required=True)
    # The first 8 digits of a CNPJ identify the legal entity; every branch
    # shares them. One root covers the whole of Travessa or Livraria da Vila;
    # a franchise like Leitura has one root PER STORE, which is why this is a
    # free-typed list and why membership is ultimately the partner's field,
    # never this list alone.
    cnpj_roots = fields.Char(
        string="CNPJ roots",
        help="First 8 digits of the CNPJs belonging to this group, separated "
             "by commas (punctuation is ignored). New partner records whose "
             "CNPJ starts with one of these are suggested into the group. "
             "A franchise network has too many roots to be worth listing -- "
             "assign its stores by hand instead.")
    partner_ids = fields.One2many('res.partner', 'partner_group_id',
                                  string="Members")
    partner_count = fields.Integer(compute='_compute_partner_count')

    _name_uniq = models.Constraint(
        'unique (name)',
        'A commercial group with this name already exists.')

    def _compute_partner_count(self):
        # O flush explícito não é decoração: num script de shell a filiação
        # recém-feita ainda mora no cache, e o SQL do _read_group contaria
        # zero -- foi assim que o seed imprimiu "0 lojas" com 13 filiadas.
        self.env['res.partner'].flush_model(['partner_group_id'])
        counts = dict(self.env['res.partner']._read_group(
            [('partner_group_id', 'in', self.ids)],
            ['partner_group_id'], ['__count']))
        for group in self:
            group.partner_count = counts.get(group, 0)

    def _root_list(self):
        """The declared roots as bare 8-digit strings, tolerant of typing."""
        self.ensure_one()
        pieces = re.split(r'[,;\s]+', self.cnpj_roots or '')
        roots = []
        for piece in pieces:
            digits = re.sub(r'\D', '', piece)
            if len(digits) == CNPJ_ROOT_DIGITS:
                roots.append(digits)
        return roots

    @api.model
    def _group_for_vat(self, vat_digits):
        """The group whose declared roots cover this document, or empty.

        Only a full CNPJ (14 digits) has a meaningful root: a CPF, a foreign
        vat or a broken document suggests nothing. Two groups claiming the
        same root would be a register mistake; the oldest wins so the answer
        is at least stable.
        """
        digits = re.sub(r'\D', '', vat_digits or '')
        if len(digits) != 14:
            return self.browse()
        root = digits[:CNPJ_ROOT_DIGITS]
        for group in self.search([('cnpj_roots', '!=', False)], order='id'):
            if root in group._root_list():
                return group
        return self.browse()

    def action_claim_matching_partners(self):
        """Pull in every ungrouped company whose CNPJ root is declared here.

        Existing membership is never overwritten: a store someone filed into
        another group stays where the person put it.
        """
        Partner = self.env['res.partner']
        for group in self:
            roots = group._root_list()
            if not roots:
                continue
            orphans = Partner.search([
                ('partner_group_id', '=', False),
                ('vat_digits', '!=', False),
            ]).filtered(lambda p: len(p.vat_digits) == 14
                        and p.vat_digits[:CNPJ_ROOT_DIGITS] in roots)
            orphans.partner_group_id = group
        # O contador não tem depends (o inverso de um One2many não invalida
        # compute sem store): quem acabou de filiar leria o número velho da
        # mesma transação -- o seed imprimiu "0 -> 0" com 140 filiadas.
        self.invalidate_recordset(['partner_count'])
        return True
