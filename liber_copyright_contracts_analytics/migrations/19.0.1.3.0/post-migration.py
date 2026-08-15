# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Mirror pre-existing royalty analytic lines into their plan column, so
    the core per-plan aggregation (account balance, plan reports) sees them."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["account.analytic.line"]._edlab_backfill_plan_columns()
