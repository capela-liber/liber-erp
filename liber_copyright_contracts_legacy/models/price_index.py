# -*- coding: utf-8 -*-
"""Price indexes (IPCA, INPC, IGP-M...) and the compounding that brings an
old amount to the money of a later month.

Convention, stated once and tested: an amount dated in month M is already in
M's prices. Correcting it to month R multiplies it by (1 + v/100) for every
month AFTER M up to and INCLUDING R. Same month (or R before M) means
factor 1 -- this module never deflates."""
import logging
from datetime import date

import requests
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BCB_URL = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.%s/dados"
           "?formato=json&dataInicial=%s&dataFinal=%s")


def month_start(day):
    return date(day.year, day.month, 1)


def compounding_factor(variations, date_from, date_to):
    """Pure function: ``variations`` maps a month-start date to its % change.

    Returns the factor that corrects an amount of ``date_from`` to
    ``date_to``. Raises ``KeyError`` with the first missing month, so the
    caller can say WHICH month the index lacks instead of silently applying a
    partial correction."""
    start = month_start(date_from)
    end = month_start(date_to)
    factor = 1.0
    month = start + relativedelta(months=1)
    while month <= end:
        if month not in variations:
            raise KeyError(month)
        factor *= 1.0 + variations[month] / 100.0
        month += relativedelta(months=1)
    return factor


class EdlabPriceIndex(models.Model):
    _name = "edlab.price.index"
    _description = "Price Index"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, help="Short code, e.g. IPCA.")
    bcb_series = fields.Integer(
        string="BCB series",
        help="Code of the series in the Central Bank of Brazil's SGS "
        "(433 = IPCA, 188 = INPC, 189 = IGP-M). Used by 'Refresh from BCB'.",
    )
    active = fields.Boolean(default=True)
    value_ids = fields.One2many("edlab.price.index.value", "index_id",
                                string="Monthly values")
    value_count = fields.Integer(compute="_compute_bounds")
    first_date = fields.Date(compute="_compute_bounds")
    last_date = fields.Date(compute="_compute_bounds",
                            help="Last month with a published variation.")

    _code_uniq = models.Constraint(
        "unique(code)", "A price index with this code already exists.")

    @api.depends("value_ids.date")
    def _compute_bounds(self):
        for index in self:
            dates = index.value_ids.mapped("date")
            index.value_count = len(dates)
            index.first_date = min(dates) if dates else False
            index.last_date = max(dates) if dates else False

    def _variations(self):
        self.ensure_one()
        return {v.date: v.variation for v in self.value_ids}

    def factor(self, date_from, date_to, variations=None):
        """Correction factor from ``date_from`` to ``date_to``; see module
        docstring. ``variations`` lets a caller that loops over many months
        read the table once."""
        self.ensure_one()
        if variations is None:
            variations = self._variations()
        try:
            return compounding_factor(variations, date_from, date_to)
        except KeyError as missing:
            raise UserError(_(
                "The index %(index)s has no value for %(month)s, so %(start)s "
                "cannot be corrected to %(to)s. Add the month (or refresh the "
                "index from the Central Bank) and try again.",
                index=self.display_name,
                month=missing.args[0].strftime("%m/%Y"),
                start=date_from.strftime("%m/%Y"),
                to=date_to.strftime("%m/%Y"))) from missing

    def action_fetch_bcb(self):
        """Pull the monthly series from the Central Bank's open API and upsert
        it. Values already stored are overwritten by the published ones
        (the IBGE occasionally revises a month)."""
        Value = self.env["edlab.price.index.value"]
        for index in self:
            if not index.bcb_series:
                raise UserError(_("Set the BCB series code on %s first.",
                                  index.display_name))
            url = BCB_URL % (index.bcb_series, "01/01/1990",
                             fields.Date.context_today(self).strftime("%d/%m/%Y"))
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise UserError(_(
                    "Could not read series %(series)s from the Central Bank "
                    "(%(error)s).", series=index.bcb_series, error=exc)) from exc
            existing = {v.date: v for v in index.value_ids}
            created = updated = 0
            for row in payload:
                try:
                    d, m, y = row["data"].split("/")
                    day = date(int(y), int(m), 1)
                    variation = float(str(row["valor"]).replace(",", "."))
                except (KeyError, ValueError, AttributeError):
                    _logger.warning("BCB row ignored: %r", row)
                    continue
                if day in existing:
                    if existing[day].variation != variation:
                        existing[day].variation = variation
                        updated += 1
                else:
                    Value.create({"index_id": index.id, "date": day,
                                  "variation": variation})
                    created += 1
            _logger.info("Price index %s: %s month(s) added, %s revised.",
                         index.code, created, updated)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Price index"),
                       "message": _("Series refreshed from the Central Bank."),
                       "type": "success"},
        }


class EdlabPriceIndexValue(models.Model):
    _name = "edlab.price.index.value"
    _description = "Price Index Monthly Value"
    _order = "date desc"

    index_id = fields.Many2one("edlab.price.index", required=True,
                               ondelete="cascade", index=True)
    date = fields.Date(required=True,
                       help="Any day of the month; stored as its first day.")
    variation = fields.Float(string="Variation (%)", digits=(12, 4),
                             required=True)

    _index_month_uniq = models.Constraint(
        "unique(index_id, date)",
        "This month is already in the index.")

    @api.depends("index_id.code", "date")
    def _compute_display_name(self):
        for value in self:
            value.display_name = "%s %s" % (
                value.index_id.code or "", value.date.strftime("%m/%Y")
                if value.date else "")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("date"):
                vals["date"] = month_start(fields.Date.to_date(vals["date"]))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("date"):
            vals["date"] = month_start(fields.Date.to_date(vals["date"]))
        return super().write(vals)
