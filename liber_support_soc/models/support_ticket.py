# -*- coding: utf-8 -*-
import base64

from odoo import _, fields, models, Command
from odoo.exceptions import UserError

from . import co_parser



class SupportTicket(models.Model):
    _inherit = 'liber.support.ticket'

    settlement_id = fields.Many2one(
        'consignment.settlement', string='Consignment (CO)', tracking=True,
        domain="[('partner_id', '=?', partner_id)]",
        help="The CO this conversation is about.")
    agreement_id = fields.Many2one(
        'consignment.agreement', string='Agreement', tracking=True,
        domain="[('partner_id', '=?', partner_id)]",
        help="The consignment agreement (AC/), when the subject is the "
             "contract itself.")

    def action_link_latest_settlement(self):
        """One click instead of a dropdown hunt: link the partner's most
        recent CO."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_(
                "Link a partner first — the CO comes from them."))
        settlement = self.env['consignment.settlement'].search(
            [('partner_id', 'child_of',
              self.partner_id.commercial_partner_id.id)],
            order='date desc, id desc', limit=1)
        if not settlement:
            raise UserError(_(
                "%s has no consignment yet.",
                self.partner_id.display_name))
        self.settlement_id = settlement

    def action_open_co_wizard(self):
        """Open the conference draft. One per ticket: if it already
        exists, come back to it exactly as it was left — checking
        something else mid-conference must not cost the work."""
        self.ensure_one()
        wizard = self.env['liber.support.co.wizard'].search(
            [('ticket_id', '=', self.id)], limit=1)
        if not wizard:
            inbound = self.message_ids.filtered(
                lambda m: m.message_type == 'email').sorted('date')
            parts = []
            for message in inbound:
                # tabelas-relatório (ex.: estoque mínimo da Olist) viram
                # linhas resolvidas (mínimo − estoque); o resto vira texto
                rest, items = co_parser.extract_report_tables(
                    str(message.body or ''))
                if items:
                    parts.append(co_parser.items_to_text(items))
                parts.append(co_parser.html_to_text(rest))
            source = '\n\n'.join(p for p in parts if p.strip())
            attachment = self.env['ir.attachment'].search(
                [('res_model', '=', self._name),
                 ('res_id', '=', self.id),
                 '|', '|', ('name', '=ilike', '%.xlsx'),
                 ('name', '=ilike', '%.csv'),
                 ('name', '=ilike', '%.pdf')],
                order='id desc', limit=1)
            wizard = self.env['liber.support.co.wizard'].create({
                'ticket_id': self.id,
                'source_text': source,
                'attachment_id': attachment.id or False,
            })
            wizard.action_parse()
        return wizard._reopen()

    def action_open_settlement(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'consignment.settlement',
            'res_id': self.settlement_id.id,
            'view_mode': 'form',
        }

    def action_reply_with_map(self):
        """Open the reply composer with the partner's consignment map
        attached — the extract of what that bookstore holds on the shelf.
        Uses the linked CO, or falls back to the partner's latest one."""
        self.ensure_one()
        settlement = self.settlement_id
        if not settlement and self.partner_id:
            settlement = self.env['consignment.settlement'].search(
                [('partner_id', 'child_of',
                  self.partner_id.commercial_partner_id.id)],
                order='date desc, id desc', limit=1)
        if not settlement:
            raise UserError(_(
                "No consignment found for this ticket: link a CO or a "
                "partner that has one."))
        report = self.env.ref(
            'liber_soc_settlement.action_report_consignment_map')
        pdf, _dummy = self.env['ir.actions.report']._render_qweb_pdf(
            report, res_ids=settlement.ids)
        attachment = self.env['ir.attachment'].create({
            'name': _('Consignment Map - %s.pdf', settlement.name),
            'type': 'binary',
            'datas': base64.b64encode(pdf),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_model': self._name,
                'default_res_ids': self.ids,
                'default_composition_mode': 'comment',
                'default_partner_ids': (
                    [Command.link(self.partner_id.id)]
                    if self.partner_id else []),
                'default_attachment_ids': [Command.link(attachment.id)],
            },
        }
