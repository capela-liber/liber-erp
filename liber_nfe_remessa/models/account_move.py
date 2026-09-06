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

    # A NOTA DE REMESSA NÃO LEVA CONTA BANCÁRIA, e por um motivo só: ninguém
    # vai pagar nada nela. Consignação não movimenta dinheiro (é valor de
    # estoque que continua nosso, na prateleira do outro) e bonificação é
    # doação. Declarar no documento a conta em que se recebe é declarar uma
    # cobrança que não existe.
    #
    # O Odoo não sabe disso. `_compute_partner_bank_id` carimba a primeira
    # conta ativa da empresa em TODA fatura de cliente, e depois `_post()`
    # recusa a nota se essa conta não estiver marcada como confiável. Foi o que
    # travou o C08577 e a bonificação INV/2026/0083 em 26/08/2026, com uma
    # mensagem sobre banco num documento que não tem banco -- e a saída que a
    # equipe encontrou foi apagar o campo à mão, nota por nota.
    #
    # Marcar a conta como confiável conserta a FATURA DE VENDA, onde há mesmo o
    # que receber. Aqui não é disso que se trata: a remessa não deve ter conta
    # nenhuma, confiável ou não.
    #
    # As dependências do core vêm repetidas de propósito: o Odoo resolve o
    # compute pelo nome, e um `@api.depends` novo substitui o de lá em vez de
    # somar-se a ele. Omitir uma faria a fatura comum parar de recalcular.
    @api.depends('bank_partner_id', 'currency_id',
                 'preferred_payment_method_line_id', 'journal_id.is_remessa')
    def _compute_partner_bank_id(self):
        remessas = self.filtered(lambda m: m.journal_id.is_remessa)
        remessas.partner_bank_id = False
        super(AccountMove, self - remessas)._compute_partner_bank_id()

    # ------------------------------------------------------------------
    # A posição fiscal de remessa exige o diário de remessa
    # ------------------------------------------------------------------
    # O espelho, na nota, da trava do pedido (liber_soc_fiscal_br): uma venda
    # não pode vestir a posição fiscal da consignação. Aqui a malandragem é a
    # mesma com outra roupa -- uma fatura no diário de VENDAS (INV/) com a
    # posição da remessa. A NF-e sai como remessa, sem imposto; a nota conta
    # como receita no diário de vendas; e ninguém a baixa, porque a baixa
    # automática só existe no diário de remessa. Cada lado, lido sozinho,
    # parece certo.
    #
    # No prod de 06/09/2026 havia 3 notas de 2026 assim na Edlab Press
    # (R$ 502 mil, entre elas a saída simbólica do FNDE lançada como venda) e
    # 2 na n-1; o legado inteiro (2019-2023) foi lançado deste jeito, porque
    # o Odoo 15 não tinha diário de remessa. O legado não se mexe; a porta
    # fecha para quem lança de hoje em diante -- e também para quem posta um
    # rascunho antigo, por isso a conferência mora no `action_post` além do
    # constrains.
    #
    # Quais posições são "de remessa" cada módulo declara em
    # `_remessa_fiscal_position_by_kind` (consignação, bonificação); o
    # `auto_invoice_paid` sozinho não serve de régua, porque a casa o marcou
    # também na devolução de venda, que é nota de venda legítima.
    @api.constrains('fiscal_position_id', 'journal_id', 'move_type')
    def _check_posicao_de_remessa_exige_diario_de_remessa(self):
        self._exigir_diario_de_remessa()

    def _exigir_diario_de_remessa(self):
        for move in self:
            if (not move.is_sale_document(include_receipts=True)
                    or move.state == 'cancel'
                    or not move.fiscal_position_id
                    or move.journal_id.is_remessa):
                continue
            de_remessa = self.env['account.fiscal.position']
            for fpos in move.company_id._remessa_fiscal_position_by_kind().values():
                de_remessa |= fpos
            if move.fiscal_position_id in de_remessa:
                raise UserError(_(
                    "%(move)s carries the remessa fiscal position %(fpos)s "
                    "but sits in %(journal)s, a sales journal.\n\n"
                    "A remessa is a note nobody pays: it books in a remessa "
                    "journal, off Invoices and off revenue. Use the remessa "
                    "journal -- or, if this is a sale, a sales fiscal "
                    "position.",
                    move=move.display_name,
                    fpos=move.fiscal_position_id.display_name,
                    journal=move.journal_id.display_name))

    def action_post(self):
        self._exigir_diario_de_remessa()
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
