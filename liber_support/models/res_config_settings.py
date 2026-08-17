# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Company-wide DEFAULT SLA targets. The team keeps its own four
    fields (each imprint may differ — the calendar already lives there);
    what Settings holds is the number a NEW team is born with. Changing
    a default here never rewrites an existing team."""
    _inherit = 'res.config.settings'

    support_sla_response_hours_normal = fields.Float(
        string='First Response (Normal)', default=8.0,
        config_parameter='liber_support.sla_response_hours_normal',
        help="Working hours a new team gets as the first-response target "
             "for normal tickets. Existing teams are not touched.")
    support_sla_response_hours_urgent = fields.Float(
        string='First Response (Urgent)', default=2.0,
        config_parameter='liber_support.sla_response_hours_urgent',
        help="Working hours a new team gets as the first-response target "
             "for urgent tickets. Existing teams are not touched.")
    support_sla_resolution_hours_normal = fields.Float(
        string='Resolution (Normal)', default=24.0,
        config_parameter='liber_support.sla_resolution_hours_normal',
        help="Working hours a new team gets as the resolution target for "
             "normal tickets. 24 working hours = 3 working days of 8 "
             "hours. Existing teams are not touched.")
    support_sla_resolution_hours_urgent = fields.Float(
        string='Resolution (Urgent)', default=8.0,
        config_parameter='liber_support.sla_resolution_hours_urgent',
        help="Working hours a new team gets as the resolution target for "
             "urgent tickets. Existing teams are not touched.")
