# -*- coding: utf-8 -*-
"""A planilha entra ao LADO do PDF, e não no lugar dele.

A primeira tentativa passava o anexo por `default_attachment_ids` no contexto
da ação. Funcionava para o CSV e matava o PDF, em silêncio: `attachment_ids`
do compositor é campo CALCULADO (a partir do template, que é de onde o
relatório vem), e valor explícito no `create` vence o cálculo. O e-mail saía
com a planilha e sem o pedido.

Aqui o cálculo roda primeiro -- trazendo o PDF -- e a planilha é somada depois.
Só para `purchase.order`: o compositor é da casa inteira, e ninguém mais tem
ficha técnica para anexar.
"""

from odoo import api, models


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    # Os dois templates de envio do pedido. A planilha anda com ELES, e não
    # com qualquer janela de e-mail aberta sobre um pedido: o "Enviar
    # mensagem" do chatter é uma conversa, não uma cotação, e chegava com a
    # ficha técnica anexada e sem texto nenhum.
    TEMPLATES = ('purchase.email_template_edi_purchase',
                 'purchase.email_template_edi_purchase_done')

    @api.depends('template_id')
    def _compute_attachment_ids(self):
        super()._compute_attachment_ids()
        do_pedido = self.env['mail.template']
        for xmlid in self.TEMPLATES:
            do_pedido |= self.env.ref(xmlid, raise_if_not_found=False) \
                or self.env['mail.template']
        for compositor in self:
            if compositor.model != 'purchase.order':
                continue
            if compositor.template_id not in do_pedido:
                continue
            pedidos = self.env['purchase.order'].browse(
                compositor._evaluate_res_ids() or []).exists()
            planilhas = self.env['ir.attachment']
            for pedido in pedidos:
                planilhas |= pedido._print_spec_attachment()
            if planilhas:
                compositor.attachment_ids = [(4, a.id) for a in planilhas]
