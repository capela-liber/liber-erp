# -*- coding: utf-8 -*-
from odoo import models

from .sale_report import NOT_REVENUE_KINDS

DOCUMENT_KIND = 'document_kind'


class SpreadsheetDashboard(models.Model):
    """The dashboard tables read sale.order straight, so they need the kind too.

    liber_soc_moves walks the dashboard and ANDs a guard into every source that
    reads `sale.order` -- today the two "by Untaxed Amount" tables of the Sales
    dashboard, which are spreadsheet lists and have no `sale.report` in
    between. Its guard is the consignment flag; this one is the fiscal kind, so
    a bonus never lands in a table of sales either.
    """
    _inherit = 'spreadsheet.dashboard'

    def _sale_order_dashboard_guards(self):
        return super()._sale_order_dashboard_guards() + [
            [DOCUMENT_KIND, 'not in', list(NOT_REVENUE_KINDS)]]
