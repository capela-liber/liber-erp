# -*- coding: utf-8 -*-
"""DANFE e XML viajam junto com a fatura no e-mail ao cliente.

O Odoo manda a fatura em PDF e para por aí. No Brasil não é a fatura que vale:
é a nota autorizada — o DANFE, que o cliente confere contra a mercadoria, e o
XML, que é o documento fiscal de verdade e o que a contabilidade dele guarda
por cinco anos. Mandar só o PDF da fatura é mandar o recibo e ficar com a nota.

O gancho é o `mail_attachments_widget` do `account.move.send`, e não o
`_get_invoice_extra_attachments`, de propósito: aquele vale para todo envio,
inclusive o "baixar", e acrescentar dois arquivos lá trocaria o download de um
PDF por um zip de três. Aqui a mudança fica onde foi pedida — no e-mail.

Entrando pelo widget, os dois documentos aparecem listados no assistente de
envio, já marcados: quem manda vê o que vai junto e pode desmarcar antes de
mandar. E o nome que aparece ali é o mesmo que o cliente vai receber.
"""

from odoo import api, models


class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    @api.model
    def _get_default_mail_attachments_widget(self, move, mail_template,
                                             invoice_edi_format=None,
                                             extra_edis=None, pdf_report=None):
        anexos = super()._get_default_mail_attachments_widget(
            move, mail_template, invoice_edi_format=invoice_edi_format,
            extra_edis=extra_edis, pdf_report=pdf_report)
        listados = {dado['id'] for dado in anexos}
        for documento in move._liber_documentos_da_nfe():
            if documento.id in listados:
                continue
            anexos.append({
                'id': documento.id,
                'name': move._liber_nome_do_documento(documento),
                'mimetype': documento.mimetype,
                'placeholder': False,
                # Anexo da nota não se apaga da fatura pelo assistente de
                # envio: desmarcar tira do e-mail, que é o que se quer poder
                # fazer. Apagar tiraria o documento fiscal do lugar onde a
                # casa o guarda.
                'protect_from_deletion': True,
            })
        return anexos

    @api.model
    def _get_mail_params(self, move, move_data):
        """Renomeia os documentos da nota no e-mail que sai.

        O `account` monta os anexos a partir do `name` gravado no
        `ir.attachment` — que é a referência da emissão. O nome de dentro fica
        como está (é ele que dá idempotência ao download e que o
        `liber_nfe_picking` procura); o que sai com outro nome é a cópia que
        viaja no e-mail.
        """
        params = super()._get_mail_params(move, move_data)
        renomear = {
            documento.name: move._liber_nome_do_documento(documento)
            for documento in move._liber_documentos_da_nfe()
        }
        if renomear:
            params['attachments'] = [
                (renomear.get(nome, nome), conteudo)
                for nome, conteudo in params.get('attachments') or []
            ]
        return params
