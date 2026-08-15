# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Re-issue of the 19.0.1.3.0 backfill under a fresh version number.

    Two parallel branches bumped the module to 19.0.1.3.0 on the same day;
    databases that upgraded through the OTHER 19.0.1.3.0 (no migrations dir)
    are already stamped with that version, so the original script will never
    fire for them. The backfill is idempotent, so databases that DID run it
    just re-run a no-op here.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["account.analytic.line"]._edlab_backfill_plan_columns()
