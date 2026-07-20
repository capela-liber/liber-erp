# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    edlab_irrf_mode = fields.Selection(
        [
            ("table", "Progressive Table"),
            ("manual", "Manual Percentage"),
            ("none", "Exempt"),
        ],
        string="IRRF Mode",
        default="table",
        help="How the withholding tax on this beneficiary's royalty payments "
        "is computed: by the official progressive table (default), by the "
        "fixed manual percentage below, or not at all (e.g. companies).",
    )

    def _edlab_royalty_statement(self, date_to=None):
        """Statement IRRF follows the withholding engine (table/exempt);
        the manual mode keeps the base behaviour (fixed percentage)."""
        res = super()._edlab_royalty_statement(date_to=date_to)
        mode = self.edlab_irrf_mode or "table"
        if mode == "manual":
            return res
        currency = res["currency"]
        if mode == "none":
            irrf = 0.0
        else:
            irrf = self.env["edlab.irrf.table"]._irrf_for_partner(
                self, res["total"], res.get("date_to")
            )
        res["irrf"] = currency.round(irrf)
        res["irrf_pct"] = (irrf / res["total"] * 100.0) if res["total"] else 0.0
        res["net"] = currency.round(res["total"] - irrf)
        return res
