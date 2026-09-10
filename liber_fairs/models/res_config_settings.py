# -*- coding: utf-8 -*-
"""As decisões que a casa toma UMA VEZ, e todo evento herda.

Três coisas que não mudam de feira para feira e que, se ficassem em cada
evento, seriam digitadas errado mais cedo ou mais tarde: onde nasce o
analítico, qual produto de serviço paga a equipe, e quem responde pelas
feiras.

As posições fiscais da remessa e do retorno moram na ponte fiscal
(`liber_fairs_nfe`), ao lado das outras configurações de nota.
"""
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fair_analytic_plan_id = fields.Many2one(
        related='company_id.fair_analytic_plan_id', readonly=False)
    fair_service_product_id = fields.Many2one(
        related='company_id.fair_service_product_id', readonly=False)
    fair_manager_id = fields.Many2one(
        related='company_id.fair_manager_id', readonly=False)
