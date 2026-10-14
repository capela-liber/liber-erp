# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    edlab_envelope_window_top = fields.Float(
        related="company_id.edlab_envelope_window_top", readonly=False)
    edlab_envelope_window_left = fields.Float(
        related="company_id.edlab_envelope_window_left", readonly=False)
    edlab_envelope_window_width = fields.Float(
        related="company_id.edlab_envelope_window_width", readonly=False)
    edlab_envelope_window_height = fields.Float(
        related="company_id.edlab_envelope_window_height", readonly=False)
    edlab_statement_header_height = fields.Float(
        related="company_id.edlab_statement_header_height", readonly=False)
