# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    special_sales_count = fields.Integer(
        string="Special Sales",
        compute="_compute_special_sales_count",
    )

    def _special_sales_domain(self):
        """Special-sale invoices selling a work this contact benefits from."""
        self.ensure_one()
        base = self.env.company._special_sales_domain()
        works = (
            self.env["edlab.contract.royalty.line"]
            .sudo()
            .search([("partner_id", "=", self.id)])
            .product_id
        )
        if ("id", "=", False) in base or not works:
            return [("id", "=", False)]
        return base + [
            ("invoice_line_ids.product_id.product_tmpl_id", "in", works.ids)
        ]

    def _compute_special_sales_count(self):
        Move = self.env["account.move"].sudo()
        for partner in self:
            partner.special_sales_count = Move.search_count(
                partner._special_sales_domain()
            )

    def action_view_special_sales(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Special Sales"),
            "res_model": "account.move",
            "domain": self._special_sales_domain(),
            "view_mode": "list,form",
            "context": {"create": False},
        }
