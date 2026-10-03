# -*- coding: utf-8 -*-
"""O CSV do mapa entra ao LADO do PDF, e não no lugar dele.

Mesmo motivo do `liber_print_quote/models/mail_compose_message.py`:
`attachment_ids` do compositor é campo CALCULADO a partir do template (que é
de onde o PDF vem), e valor explícito no `create` venceria o cálculo -- o
e-mail sairia com o CSV e sem o mapa.

Só entra quando o template é o do mapa de consignação: o "Enviar mensagem" do
chatter é uma conversa, não um mapa, e não deve carregar planilha nenhuma.
"""

from odoo import api, models


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    @api.depends('template_id')
    def _compute_attachment_ids(self):
        super()._compute_attachment_ids()
        template = self.env.ref(
            'liber_soc_settlement.mail_template_consignment_map',
            raise_if_not_found=False)
        if not template:
            return
        for compositor in self:
            if compositor.model != 'consignment.settlement':
                continue
            if compositor.template_id != template:
                continue
            cos = self.env['consignment.settlement'].browse(
                compositor._evaluate_res_ids() or []).exists()
            anexos = self.env['ir.attachment']
            for co in cos:
                anexos |= co._map_csv_attachment()
            if anexos:
                compositor.attachment_ids = [(4, a.id) for a in anexos]
