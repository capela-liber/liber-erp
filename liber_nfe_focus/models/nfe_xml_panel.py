# -*- coding: utf-8 -*-

from odoo import fields, models


class NfeXmlPanel(models.Model):
    """A procedência da nota que a casa mesmo emitiu.

    O painel é agnóstico de origem de propósito -- um XML é um XML, venha de
    onde vier --, mas saber QUEM o trouxe é o que separa um import ruim de um
    mistério. Só que todas as origens que existiam eram de nota que CHEGA: o
    upload manual, o cron de anexo, a varredura da SEFAZ, a API do Olist. A
    nota que SAI daqui não era nenhuma delas e caía no padrão, "Manual Upload"
    -- o painel dizia que alguém tinha subido à mão a nota que a casa acabara
    de emitir.

    O rótulo é o do adaptador, não o do documento: quem falou com a SEFAZ
    nesta emissão foi a Focus. Se um dia a casa emitir por outro caminho (o
    Olist é o candidato), esse caminho ganha o seu próprio valor e as notas
    continuam distinguíveis uma a uma.
    """
    _inherit = 'nfe.xml.panel'

    source = fields.Selection(selection_add=[('focus', 'Focus NFe')],
                              ondelete={'focus': 'set default'})
