# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    transport_pickup_request_text = fields.Html(
        related='company_id.transport_pickup_request_text', readonly=False)
