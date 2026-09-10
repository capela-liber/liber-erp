# -*- coding: utf-8 -*-
from odoo import api, models


class NfeXmlPanel(models.Model):
    """O painel avisa a logística quando vira a nota de uma fatura.

    A fatura que nasce de XML importado (Olist e afins) não passa pela Focus,
    então o gancho da autorização nunca carimba a nota nas transferências.
    O momento certo é este: quando o painel ganha a fatura, a nota chega ao
    mov -- e o operador imprime a DANFE sem saber de onde a nota veio.
    """
    _inherit = 'nfe.xml.panel'

    @api.model_create_multi
    def create(self, vals_list):
        panels = super().create(vals_list)
        panels.invoice_id._liber_carimbar_pickings_do_xml()
        return panels

    def write(self, vals):
        res = super().write(vals)
        if vals.get('invoice_id'):
            self.invoice_id._liber_carimbar_pickings_do_xml()
        return res
