# -*- coding: utf-8 -*-
from odoo import models


class SaleReport(models.Model):
    """Keep consignment orders (Pedidos C) out of Sales Analysis entirely.

    Overriding the report's WHERE clause excludes them from EVERY sale.report
    view at once (present and future), so no sales report ever counts a
    consignment as a sale -- the isolation is by construction, not by per-view
    filters that leak over time.
    """
    _inherit = 'sale.report'

    def _where_sale(self):
        return super()._where_sale() + " AND s.is_consignment IS NOT TRUE"
