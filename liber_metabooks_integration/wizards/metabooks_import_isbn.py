# -*- coding: utf-8 -*-
import re

from odoo import _, fields, models
from odoo.exceptions import UserError


class MetabooksImportIsbn(models.TransientModel):
    _name = "metabooks.import.isbn"
    _description = "Import products from Metabooks by ISBN"

    isbns = fields.Text(
        string="ISBNs",
        help="Paste one or more ISBNs (one per line, or separated by comma/space).",
    )

    def action_import(self):
        self.ensure_one()
        raw = self.isbns or ""
        codes = [c for c in re.split(r"[\s,;]+", raw) if c.strip()]
        if not codes:
            raise UserError(_("Enter at least one ISBN."))
        result = self.env["metabooks.connector"].import_isbns(codes)
        products = result["products"]
        if not products:
            raise UserError(_("No product was found on Metabooks for the given ISBN(s)."))
        # Summarise so the user sees existing books were updated, not duplicated.
        name = _("Metabooks import — %(new)s new, %(updated)s updated") % {
            "new": result["created"], "updated": result["updated"]}
        if result["not_found"]:
            name += _(" (%s not found)") % len(result["not_found"])
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "product.template",
            "domain": [("id", "in", products.ids)],
            "view_mode": "list,form",
            "target": "current",
        }
