# -*- coding: utf-8 -*-
import pytz

from odoo import fields, models


class SaleReport(models.Model):
    """The day of the order, in the timezone of whoever is looking.

    The core `date` is a UTC datetime. A spreadsheet grouping it by month
    converts midnight of the 1st to the local timezone and lands on the 31st
    of the previous month at 9 pm: the dashboard table called "August 2025"
    what the chart, right above it, called "September 2025" (Edlab Press,
    staging, 06/09/2026). A Date field has no midnight to get wrong.
    """
    _inherit = 'sale.report'

    order_date = fields.Date(string="Order Day", readonly=True)

    def _user_timezone(self):
        """The timezone name, checked against pytz before it goes into SQL --
        it comes from the user, and SQL takes no unchecked text."""
        tz = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        return tz if tz in pytz.all_timezones_set else 'UTC'

    def _sql_order_date(self):
        return ("(s.date_order AT TIME ZONE 'UTC' AT TIME ZONE '%s')::date"
                % self._user_timezone())

    def _select_additional_fields(self):
        additional = super()._select_additional_fields()
        additional['order_date'] = self._sql_order_date()
        return additional

    def _group_by_sale(self):
        # `s.date_order` is already grouped by the core; the expression over
        # it is valid, but it is listed so Postgres does not have to infer it.
        return super()._group_by_sale() + ", " + self._sql_order_date()
