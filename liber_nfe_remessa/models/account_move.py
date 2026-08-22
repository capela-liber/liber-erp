# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    # The settlement entry this note generated (and vice versa), so both
    # directions are one click and the pair reads as a single fiscal fact.
    remessa_settle_move_id = fields.Many2one(
        'account.move', string="Remessa settlement", readonly=True, copy=False)

    # Who fired this remessa. Every module that generates remessa notes adds
    # its value (selection_add): the comp-copies module adds 'bonus', soc adds
    # 'consignment', the future events module adds 'event'. The Remessas menu
    # filters and groups on it -- one list, separable origins.
    remessa_origin = fields.Selection(
        [('other', "Other")], string="Remessa origin",
        default='other', readonly=True, copy=False, index=True)

    # For the form view: ribbons cannot dot through journal_id, and the "Paid"
    # ribbon on a remessa is semantically absurd -- a simples remessa can never
    # be paid because nothing was ever owed. The ledger says paid (the
    # receivable was settled); the screen must not.
    is_remessa_note = fields.Boolean(
        related='journal_id.is_remessa', string="Is remessa note")

    def action_post(self):
        res = super().action_post()
        for move in self:
            if (move.journal_id.is_remessa
                    and move.is_sale_document(include_receipts=True)
                    and not move.remessa_settle_move_id):
                move._remessa_auto_settle()
        return res

    def _remessa_auto_settle(self):
        """Settle the receivable so the note never asks for payment.

        A remessa is value without a debt: the nota must exist (Brazil bills
        every movement, even giving books away), but nobody owes anything.
        Post-then-settle is the only shape O19 allows for that.
        """
        self.ensure_one()
        fpos = self.fiscal_position_id
        if not fpos.auto_invoice_paid:
            raise UserError(_(
                "Journal %(journal)s is a remessa journal, but fiscal position "
                "%(fpos)s does not have Auto Invoice Paid configured. A "
                "remessa note that asks for payment is a contradiction -- "
                "configure the fiscal position (or use a regular sales "
                "journal).",
                journal=self.journal_id.display_name,
                fpos=fpos.display_name or _("(none)")))
        if not fpos.auto_invoice_paid_account_id:
            raise UserError(_(
                "Fiscal position %s has Auto Invoice Paid but no counterpart "
                "account.", fpos.display_name))
        term_lines = self.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable')
        if not term_lines:
            return
        counter = fpos.auto_invoice_paid_account_id
        # The settlement is bookkeeping, not a fiscal document: it must NOT
        # consume a REM/ number (a fiscal sequence with holes -- REM/00001,
        # 00003, 00005 -- reads as missing notes). It books in a general
        # journal; the note keeps the contiguous sequence.
        misc = self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.company_id.id)],
            limit=1) or self.journal_id
        settle = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': misc.id,
            'date': self.date,
            'ref': _("Auto settlement of %s", self.name),
            'line_ids': [
                (0, 0, {
                    'account_id': counter.id,
                    'partner_id': self.partner_id.id,
                    'name': _("Remessa -- %s", self.name),
                    'debit': sum(term_lines.mapped('debit')),
                    'credit': sum(term_lines.mapped('credit')),
                }),
                (0, 0, {
                    'account_id': term_lines[0].account_id.id,
                    'partner_id': self.partner_id.id,
                    'name': _("Remessa -- %s", self.name),
                    'debit': sum(term_lines.mapped('credit')),
                    'credit': sum(term_lines.mapped('debit')),
                    'date_maturity': self.date,
                }),
            ],
        })
        settle.action_post()
        (term_lines + settle.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )).reconcile()
        self.remessa_settle_move_id = settle

    def button_cancel(self):
        """Cancelar a nota leva junto a baixa que a quitou.

        As duas nasceram do mesmo fato e só fazem sentido juntas: a baixa
        existe para dizer que aquela nota não cobra nada. Cancelada a nota, uma
        baixa lançada sozinha é meia contabilidade em pé -- e foi o que obrigou
        a desfazer um cancelamento na unha, no banco, em 21/08.

        O `unlink` já era guardado pelo mesmo motivo (`_unlink_never_orphan_
        settlement`); faltava o cancelamento, que é o caminho que se usa de
        verdade quando a NF-e é cancelada na SEFAZ.
        """
        baixas = self.remessa_settle_move_id.filtered(
            lambda m: m.state == 'posted')
        if baixas:
            baixas.button_draft()
            baixas.button_cancel()
        return super().button_cancel()

    @api.ondelete(at_uninstall=False)
    def _unlink_never_orphan_settlement(self):
        # Deleting a note whose settlement stays posted would leave a dangling
        # half of the pair.
        for move in self:
            if move.remessa_settle_move_id.state == 'posted':
                raise UserError(_(
                    "%(note)s has a posted settlement entry (%(settle)s). "
                    "Reverse or reset it first.",
                    note=move.name, settle=move.remessa_settle_move_id.name))

    def action_view_remessa_settlement(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.remessa_settle_move_id.id,
            'view_mode': 'form',
        }
