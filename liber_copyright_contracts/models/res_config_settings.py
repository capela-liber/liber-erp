# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # General (company-independent) default: backed by a system parameter, not a
    # per-company field, so a single value applies across the whole database.
    contract_expiry_reminder_days = fields.Integer(
        string="Contract expiry reminder (days)",
        default=45,
        config_parameter="copyright_contracts.expiry_reminder_days",
        help="How many days before a contract's expiration date the daily job "
             "creates a reminder activity for the responsible user.",
    )
