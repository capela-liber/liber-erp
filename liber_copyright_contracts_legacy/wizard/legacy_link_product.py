# -*- coding: utf-8 -*-
"""Link the selected legacy rows to a product: the rows the ISBN did not
reach (30.000 'SEM_ISBN' lines carry only a title) get their work by hand,
a title at a time, from the list."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EdlabLegacyLinkProduct(models.TransientModel):
    _name = "edlab.legacy.link.product"
    _description = "Link legacy rows to a product"

    sale_ids = fields.Many2many(
        "edlab.legacy.sale", default=lambda self: self.env.context.get("active_ids"))
    sale_count = fields.Integer(compute="_compute_sale_count")
    product_id = fields.Many2one("product.product", required=True)
    same_title = fields.Boolean(
        string="Also the other rows with these titles",
        default=True,
        help="Extend the link to every row without a product that has the "
        "same original title (or internal code) as a selected row.")

    @api.depends("sale_ids")
    def _compute_sale_count(self):
        for wizard in self:
            wizard.sale_count = len(wizard.sale_ids)

    def action_link(self):
        self.ensure_one()
        if not self.sale_ids:
            raise UserError(_("Select the rows to link first."))
        rows = self.sale_ids
        if self.same_title:
            Sale = self.env["edlab.legacy.sale"]
            titles = {t for t in rows.mapped("title_original") if t}
            codes = {c for c in rows.mapped("internal_code") if c}
            domain = [("product_id", "=", False)]
            if titles and codes:
                domain += ["|", ("title_original", "in", list(titles)),
                           ("internal_code", "in", list(codes))]
            elif titles:
                domain.append(("title_original", "in", list(titles)))
            elif codes:
                domain.append(("internal_code", "in", list(codes)))
            rows |= Sale.search(domain)
        rows.write({"product_id": self.product_id.id})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Legacy sales"),
                       "message": _("%(n)s row(s) linked to %(p)s.",
                                    n=len(rows), p=self.product_id.display_name),
                       "type": "success", "next": {"type": "ir.actions.act_window_close"}},
        }
