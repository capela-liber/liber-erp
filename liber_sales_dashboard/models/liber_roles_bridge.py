# -*- coding: utf-8 -*-
"""A demonstração vê os painéis de Vendas e de Produto (12/10/2026).

Os dois painéis do core, e o menu "Notas fiscais" de Vendas, são trancados no
Gerente de Vendas -- grupo que o visitante do liber_roles retira de propósito
(ele traz configuração junto). O mapa do Brasil por UF (liber_geo_brasil), os
dois relógios deste módulo e o Top 50 (liber_dashboard_top) moram nesses
painéis: sem esta ponte, a vitrine não mostrava nenhum deles.

A concessão é de LEITURA da tela, e mora aqui pelo mesmo motivo da ponte do
liber_support: citar o grupo do liber_roles em XML seria dependência de
módulo. Sem o liber_roles instalado, é no-op. O grupo se SOMA ao que já está
nos painéis e no menu -- (4, ...) --, então o Gerente segue vendo tudo.
"""
from odoo import api, models

#: o que a demonstração passa a ver, por XML id
PAINEIS = (
    'spreadsheet_dashboard_sale.spreadsheet_dashboard_sales',
    'spreadsheet_dashboard_sale.spreadsheet_dashboard_product',
)
MENUS = ('liber_sales_dashboard.menu_notas_fiscais',)


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _liber_sales_dashboard_ligar_no_visitante(self):
        visitante = self.env.ref('liber_roles.group_visitante',
                                 raise_if_not_found=False)
        if not visitante:
            return
        for xmlid in PAINEIS + MENUS:
            registro = self.env.ref(xmlid, raise_if_not_found=False)
            if registro:
                registro.sudo().write({'group_ids': [(4, visitante.id)]})
