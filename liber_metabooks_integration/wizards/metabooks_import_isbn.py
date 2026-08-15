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

    # The wizard reopens on itself with the outcome: the codes that failed used
    # to reach only the server log, so whoever pasted 30 ISBNs and read
    # "(3 not found)" in the window title had to check them one by one.
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Done")], default="draft", readonly=True)
    summary = fields.Text(readonly=True)
    not_found_isbns = fields.Text(string="Not found on Metabooks", readonly=True)
    failed_details = fields.Text(string="Failed", readonly=True)
    product_ids = fields.Many2many("product.template", readonly=True)

    def action_import(self):
        self.ensure_one()
        raw = self.isbns or ""
        codes = [c for c in re.split(r"[\s,;]+", raw) if c.strip()]
        if not codes:
            raise UserError(_("Enter at least one ISBN."))
        result = self.env["metabooks.connector"].import_isbns(codes)

        counts = [
            (result["created"], _("%s new")),
            (result["updated"], _("%s updated")),
            (len(result["not_found"]), _("%s not found on Metabooks")),
            (len(result["failed"]), _("%s failed")),
        ]
        summary = "\n".join(label % n for n, label in counts if n)
        self.write({
            "state": "done",
            "summary": summary or _("Nothing imported."),
            "not_found_isbns": "\n".join(result["not_found"]) or False,
            "failed_details": "\n".join(
                "%s - %s" % (isbn, msg) for isbn, msg in result["failed"]) or False,
            "product_ids": [(6, 0, result["products"].ids)],
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Import from Metabooks (ISBN)"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_view_products(self):
        """Open the books this import created or updated."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Books from Metabooks"),
            "res_model": "product.template",
            "domain": [("id", "in", self.product_ids.ids)],
            "view_mode": "list,form",
            "target": "current",
        }

    def action_retry_failed(self):
        """Put the codes that failed back in the box for another go."""
        self.ensure_one()
        retry = [line.split(" - ")[0]
                 for line in (self.failed_details or "").splitlines() if line]
        if not retry:
            raise UserError(_("Nothing to retry."))
        self.write({
            "state": "draft",
            "isbns": "\n".join(retry),
            "summary": False,
            "not_found_isbns": False,
            "failed_details": False,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
