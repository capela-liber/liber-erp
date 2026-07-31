# -*- coding: utf-8 -*-
"""Carta de Correção Eletrônica (CC-e).

Duas regras da SEFAZ que a tela precisa deixar claras, porque quem emite não
costuma saber:

1. **A carta não corrige tudo.** Ela conserta erro de redação — descrição do
   produto, dados de transporte, informações complementares. Valor, imposto,
   data de emissão, remetente e destinatário **não** se corrigem por carta: a
   nota errada se cancela e se emite outra.

2. **Cada carta SUBSTITUI a anterior.** Não são emendas que se somam: a última
   vale por inteiro. Quem manda a segunda carta esquecendo o que dizia a
   primeira acabou de revogar a primeira correção. Por isso o assistente mostra
   o histórico e já vem preenchido com o texto anterior.
"""

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.focus_client import FocusError

# A SEFAZ aceita no máximo 20 cartas por nota.
MAX_CARTAS = 20


class NfeFocusCorrecaoWizard(models.TransientModel):
    _name = 'nfe.focus.correcao.wizard'
    _description = 'Carta de Correção Eletrônica'

    move_id = fields.Many2one(
        'account.move', string='Fatura', required=True, readonly=True)
    correcao = fields.Text(
        string='Texto da correção', required=True,
        default=lambda self: self._default_correcao(),
        help="Entre 15 e 1000 caracteres. Vai para a SEFAZ como está e "
             "SUBSTITUI qualquer carta anterior desta nota.")
    historico = fields.Text(
        string='Cartas anteriores', readonly=True,
        default=lambda self: self._default_historico())

    @api.model
    def _default_move(self):
        return self.env['account.move'].browse(
            self.env.context.get('default_move_id'))

    @api.model
    def _default_historico(self):
        return self._default_move().focus_correcoes or False

    @api.model
    def _default_correcao(self):
        """Vem preenchido com a última carta.

        Porque a nova substitui a anterior: começar de um campo vazio convida a
        escrever só o acréscimo e, sem perceber, apagar a correção que já valia.
        """
        historico = self._default_move().focus_correcoes
        if not historico:
            return False
        # O histórico guarda "[data] texto" por bloco, mais recente por último.
        ultima = historico.rstrip().split('\n\n')[-1]
        return ultima.split('] ', 1)[-1] if '] ' in ultima else ultima

    def action_enviar(self):
        self.ensure_one()
        move = self.move_id
        anteriores = (move.focus_correcoes or '').count('\n\n') + 1 \
            if move.focus_correcoes else 0
        if anteriores >= MAX_CARTAS:
            raise UserError(_(
                "%(fatura)s já tem %(n)s cartas de correção, que é o limite da "
                "SEFAZ.", fatura=move.display_name, n=anteriores))

        try:
            move._focus_client_da_nota().carta_correcao(
                move.focus_ref, self.correcao)
        except FocusError as exc:
            raise UserError(_("Focus NFe: %s", exc.message)) from exc

        # A carta também vira XML de evento, e ele só aparece na consulta.
        try:
            move.action_focus_consultar()
        except Exception:  # noqa: BLE001 - a carta já foi aceita
            pass

        carimbo = fields.Datetime.to_string(fields.Datetime.now())
        bloco = '[%s] %s' % (carimbo, self.correcao.strip())
        move.write({
            'focus_correcoes': '\n\n'.join(
                filter(None, [move.focus_correcoes, bloco])),
        })
        move.message_post(body=Markup(_(
            "<p><b>Carta de correção enviada à SEFAZ.</b> Ela substitui as "
            "anteriores.</p><p>%(texto)s</p>")) % {'texto': self.correcao})
        return {'type': 'ir.actions.act_window_close'}
