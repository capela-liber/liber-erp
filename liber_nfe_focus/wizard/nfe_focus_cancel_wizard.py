# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError

from ..models.focus_client import FocusError


class NfeFocusCancelWizard(models.TransientModel):
    _name = 'nfe.focus.cancel.wizard'
    _description = 'Cancelamento de NFe na Focus'

    move_id = fields.Many2one(
        'account.move', string='Fatura', required=True, readonly=True)
    justificativa = fields.Text(
        string='Justificativa', required=True,
        help="Vai para a SEFAZ como está. Entre 15 e 255 caracteres.")

    def action_cancelar(self):
        """Cancela na SEFAZ. Síncrono: a resposta já é o resultado."""
        self.ensure_one()
        move = self.move_id
        try:
            resposta = move._focus_client_da_nota().cancelar_nfe(
                move.focus_ref, self.justificativa)
        except FocusError as exc:
            raise UserError(_("Focus NFe: %s", exc.message)) from exc

        # O cancelamento devolve o documento já com o novo status; aplicar a
        # resposta inteira mantém protocolo e mensagem coerentes com a SEFAZ.
        move._focus_aplicar_resposta(resposta)
        # E depois consulta: o caminho do XML do evento só aparece na consulta
        # completa, não na resposta imediata do cancelamento -- e é esse XML que
        # o painel de XMLs precisa receber.
        try:
            move.action_focus_consultar()
        except UserError:
            pass
        move.message_post(body=_(
            "NFe cancelada na SEFAZ. Justificativa: %s", self.justificativa))
        return {'type': 'ir.actions.act_window_close'}
