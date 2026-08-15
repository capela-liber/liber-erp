# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    transport_pickup_request_text = fields.Html(
        string='Pickup Request Text',
        help="Standard intro text of the pickup-request e-mail sent to the "
             "carrier. Leave empty to use the built-in default. Editable in "
             "the Transport settings.")
