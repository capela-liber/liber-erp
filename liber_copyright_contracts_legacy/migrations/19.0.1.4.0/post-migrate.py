# -*- coding: utf-8 -*-
"""Fill the new discount (%) on the rows already imported.

The import and the classification compute it from now on; the half a
million rows of a base imported before 19.0.1.4.0 get it here, in one
UPDATE, with the same expression."""
import logging

from odoo.addons.liber_copyright_contracts_legacy.models.legacy_sale import (
    DISCOUNT_PERCENT_SQL,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("UPDATE edlab_legacy_sale s SET discount_percent = %s"
               % DISCOUNT_PERCENT_SQL)
    _logger.info("Legacy sales: discount (%%) filled on %s row(s)", cr.rowcount)
