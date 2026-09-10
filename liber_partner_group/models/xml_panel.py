# -*- coding: utf-8 -*-
from odoo import fields, models


class NfeXmlPanel(models.Model):
    _inherit = 'nfe.xml.panel'

    # STORED porque agrupar exige coluna (o mesmo motivo do
    # `consignment_partner_id` do estoque consignado): um related sem store
    # não tem o que o GROUP BY ler. O related mantém a coluna em dia quando a
    # ficha muda de rede.
    partner_group_id = fields.Many2one(
        related='partner_id.partner_group_id', string="Commercial Group",
        store=True, readonly=True)
    commercial_group_display = fields.Char(
        related='partner_id.commercial_group_display',
        string="Group / Client", store=True, readonly=True)
