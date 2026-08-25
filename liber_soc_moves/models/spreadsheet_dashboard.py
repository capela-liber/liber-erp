# -*- coding: utf-8 -*-
import json

from odoo import models

# Where the Pedido C lives, and the flag that tells it apart from a sale.
SALE_ORDER = 'sale.order'
IS_CONSIGNMENT = 'is_consignment'

# The guard put on every dashboard source that reads sale.order directly.
# `= False` and not `!= True`: for a boolean that is the Odoo idiom, and it is
# the one that also matches the rows where the column is NULL.
GUARD = [IS_CONSIGNMENT, '=', False]


class SpreadsheetDashboard(models.Model):
    """Consignment stays out of the dashboards too, not only of the reports.

    `sale_report.py` keeps the Pedido C out of Sales Analysis by overriding the
    report's WHERE clause, so every card and every chart of the Sales dashboard
    is already clean -- they all read `sale.report`. The two "by Untaxed
    Amount" tables at the bottom are not: those are spreadsheet *lists*, and a
    list reads `sale.order` straight, with no report in between. The dashboard
    was saying consignment is not a sale at the top and counting it at the
    bottom -- and, the orders being large, consignment took four of the ten
    lines of the table.

    What does NOT leave, and must not: the S born of the Acerto. The settlement
    creates a plain sale.order (`consignment_settlement._create_sale_order`),
    unflagged on purpose -- that document IS the sale, and it is where the
    consignment finally becomes revenue.

    The guard is added on READ, not to the stored spreadsheet, for the same
    reason liber_geo_brasil does it that way: the `spreadsheet_dashboard_sale`
    record is not `noupdate`, so every upgrade of that module rewrites the JSON
    and would drop an edit of ours without a word.

    What this does NOT cover: a source whose domain is stored as TEXT
    (o_spreadsheet writes some chart domains that way). No core dashboard has a
    sale.order chart -- only the two lists -- and parsing a domain out of a
    string to write it back is a bigger promise than this is worth.
    """
    _inherit = 'spreadsheet.dashboard'

    def _sale_order_dashboard_guards(self):
        """The terms every dashboard source reading sale.order is ANDed with.

        This is the extension point, and the reason it exists is that "not a
        sale" has more than one axis: consignment is a flag on the order, and
        the CFOP kinds (a bonus is given, a book at a fair comes back) are a
        field of their own. liber_soc_fiscal_br adds its term here, so the
        walking and the rewriting below are written once.
        """
        return [list(GUARD)]

    def _get_serialized_readonly_dashboard(self):
        serialized = super()._get_serialized_readonly_dashboard()
        data = json.loads(serialized)
        snapshot = data.get('snapshot') or {}
        guards = self._sale_order_dashboard_guards()
        # A list, and not a generator: every source has to get the guards, and
        # `any()` over a generator would stop at the first one that changed.
        changed = [self._guard_sale_order_source(source, guards)
                   for source in self._sale_order_sources(snapshot)]
        if any(changed):
            return json.dumps(data)
        return serialized

    def _sale_order_sources(self, snapshot):
        """The places a dashboard can read `sale.order` from.

        A list and a pivot carry the model and the domain in the same dict; a
        chart splits them -- the model is in `metaData.resModel` and the domain
        in `searchParams`. What is yielded is always the dict that holds the
        domain.
        """
        for group in ('lists', 'pivots'):
            for source in (snapshot.get(group) or {}).values():
                if isinstance(source, dict) and source.get('model') == SALE_ORDER:
                    yield source
        for sheet in snapshot.get('sheets') or []:
            if not isinstance(sheet, dict):
                continue
            for figure in sheet.get('figures') or []:
                data = figure.get('data') if isinstance(figure, dict) else None
                if not isinstance(data, dict):
                    continue
                # A figure is either one chart or a carousel of several.
                definitions = data.get('chartDefinitions')
                charts = [data] if definitions is None else list(definitions.values())
                for chart in charts:
                    if not isinstance(chart, dict):
                        continue
                    meta = chart.get('metaData') or {}
                    params = chart.get('searchParams')
                    if (isinstance(meta, dict) and meta.get('resModel') == SALE_ORDER
                            and isinstance(params, dict)):
                        yield params

    def _guard_sale_order_source(self, source, guards):
        """AND the guards into one source's domain. Returns whether it changed.

        Everything already in the domain stays: the dashboard's own `state`
        filter is what makes the table a table of orders, and dropping it to
        write ours would be trading one wrong number for another.
        """
        if not isinstance(source, dict):
            return False
        domain = source.get('domain') or []
        if not isinstance(domain, list):
            return False
        missing = [guard for guard in guards if not self._has_term(domain, guard)]
        if not missing:
            return False
        # Odoo domains are prefix notation: one "&" per operand added, minus
        # the one the original domain itself supplies (none, if it was empty).
        joins = len(missing) if domain else len(missing) - 1
        source['domain'] = ['&'] * joins + domain + missing
        return True

    @staticmethod
    def _has_term(domain, term):
        return any(isinstance(other, (list, tuple)) and list(other) == term
                   for other in domain)
