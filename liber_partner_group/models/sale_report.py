# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleReport(models.Model):
    _inherit = 'sale.report'

    # O eixo que faltava na Análise de Vendas: o núcleo expõe a loja
    # (`partner_id`) e o `commercial_partner_id` -- que para filial com CNPJ
    # próprio é a própria loja. A rede entra pelo JOIN de parceiro que o
    # núcleo já faz (`_from_sale` junta `res_partner partner`).
    partner_group_id = fields.Many2one(
        'liber.partner.group', string="Commercial Group", readonly=True)
    # O eixo sem "Nenhum": rede ou o próprio cliente. Coluna física de
    # res_partner (compute stored), então entra no SELECT sem JOIN novo.
    commercial_group_display = fields.Char(
        string="Group / Client", readonly=True)

    def _select_additional_fields(self):
        additional = super()._select_additional_fields()
        additional['partner_group_id'] = "partner.partner_group_id"
        additional['commercial_group_display'] = "partner.commercial_group_display"
        return additional

    def _group_by_sale(self):
        return (super()._group_by_sale()
                + ", partner.partner_group_id"
                + ", partner.commercial_group_display")
