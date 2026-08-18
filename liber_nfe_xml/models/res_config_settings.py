# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Por empresa, e não chave global: `account.fiscal.position` carrega
    # `company_id`, então um id só valeria numa empresa -- a casa tem seis.
    sale_fiscal_position_id = fields.Many2one(
        related='company_id.sale_fiscal_position_id', readonly=False)
