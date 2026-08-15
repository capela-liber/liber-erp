# -*- coding: utf-8 -*-
from odoo import fields, models


class SupportStage(models.Model):
    """A kanban column. Global (not per-team) on purpose: three teams,
    one workflow — per-team stages would triple the config for nothing."""
    _name = 'liber.support.stage'
    _description = 'Support Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(
        string='Folded in Kanban',
        help="Folded columns hold finished work: Resolved, Closed, Spam.")
    # The two flags the SLA engine reads. A stage may pause the clock
    # (Waiting Customer) or stop it for good (Resolved/Closed/Spam).
    pause_sla = fields.Boolean(
        string='Pauses SLA',
        help="While a ticket sits here the resolution clock does not run "
             "(the ball is in the customer's court).")
    is_closed = fields.Boolean(
        string='Closing Stage',
        help="Entering this stage stamps the closing date and freezes "
             "both SLA clocks.")
