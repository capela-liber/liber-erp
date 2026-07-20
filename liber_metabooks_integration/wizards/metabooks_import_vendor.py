# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class MetabooksImportVendor(models.TransientModel):
    _name = "metabooks.import.vendor"
    _description = "Import a publisher catalogue from Metabooks by Vendor/MVB ID"

    mvb_id = fields.Char(
        string="Vendor / MVB ID",
        required=True,
        help="Metabooks publisher id (VL / mvbId), e.g. BR0089701.",
    )
    limit = fields.Integer(
        string="Limit",
        default=0,
        help="Max number of products to import (0 = whole catalogue). "
             "Use a small number to test first.",
    )
    with_covers = fields.Boolean(string="Download covers", default=True)
    with_technical = fields.Boolean(
        string="Download technical sheets", default=False,
        help="Also fetch each book's technical sheet (dimensions, weight, page "
             "count, binding, NCM) after the catalogue import — one by-ISBN call "
             "per book, run as a follow-up background job.")

    def action_import(self):
        self.ensure_one()
        if not self.mvb_id:
            raise UserError(_("Enter a Vendor / MVB ID."))
        job = self.env["metabooks.import.job"].create_and_run(
            self.mvb_id.strip(), with_covers=self.with_covers, limit=self.limit or 0,
            with_technical=self.with_technical)
        return job.open_form_action()
