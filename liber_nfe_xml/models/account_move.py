# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

NFE_KEY_RE = re.compile(r'^\d{44}$')


class AccountMove(models.Model):
    _inherit = 'account.move'

    # The NFe access key (chave de acesso) is the business identifier that
    # ties an Odoo invoice/bill to the fiscal document it came from. The
    # Many2one below is resolved THROUGH this key, never through the
    # database id, so the link survives exports, imports and DB restores
    # and can always be rebuilt from the documents themselves.
    nfe_key = fields.Char(
        string='NFe Access Key', size=44, copy=False, tracking=True,
        index='btree_not_null',
        help="44-digit access key (chave de acesso) of the NFe this "
             "invoice/bill was created from. This key - not the database "
             "id - is what links the move to its NFe XML panel record.")
    nfe_xml_panel_id = fields.Many2one(
        'nfe.xml.panel', string='NFe XML',
        compute='_compute_nfe_xml_panel_id',
        inverse='_inverse_nfe_xml_panel_id',
        store=True, copy=False,
        help="NFe XML panel record holding the source XML. Resolved by the "
             "NFe access key; to unlink a move that has a key, clear the "
             "key itself.")
    nfe_danfe_no = fields.Char(
        related='nfe_xml_panel_id.danfe_no', string='DANFE No.')

    @api.depends('nfe_key')
    def _compute_nfe_xml_panel_id(self):
        Panel = self.env['nfe.xml.panel']
        for move in self:
            if move.nfe_key:
                move.nfe_xml_panel_id = Panel.search(
                    [('key', '=', move.nfe_key)], limit=1)
            else:
                # keep a manually set panel (legacy XMLs without access key)
                move.nfe_xml_panel_id = move.nfe_xml_panel_id

    def _inverse_nfe_xml_panel_id(self):
        for move in self:
            if move.nfe_xml_panel_id.key:
                move.nfe_key = move.nfe_xml_panel_id.key

    @api.constrains('nfe_key')
    def _check_nfe_key(self):
        for move in self:
            if move.nfe_key and not NFE_KEY_RE.match(move.nfe_key):
                raise ValidationError(_(
                    "The NFe access key must have exactly 44 digits "
                    "(got %r).") % move.nfe_key)

    @api.constrains('nfe_key', 'move_type', 'state')
    def _check_nfe_key_unique(self):
        for move in self:
            if not move.nfe_key or move.state == 'cancel':
                continue
            duplicate = self.search(
                [('id', '!=', move.id),
                 ('nfe_key', '=', move.nfe_key),
                 ('move_type', '=', move.move_type),
                 ('state', '!=', 'cancel')], limit=1)
            if duplicate:
                raise ValidationError(_(
                    "%(dup)s already uses the NFe access key %(key)s. Two "
                    "non-cancelled moves of the same type cannot come from "
                    "the same NFe.",
                    dup=duplicate.display_name, key=move.nfe_key))

    def action_open_nfe_xml_panel(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('NFe XML'),
            'res_model': 'nfe.xml.panel',
            'res_id': self.nfe_xml_panel_id.id,
            'view_mode': 'form',
        }
