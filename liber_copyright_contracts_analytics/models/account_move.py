# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    # The 'sale' module defines the same field; we only depend on the lighter
    # 'sales_team', so we add it here to tag an invoice's sales team. If 'sale'
    # is installed later, both definitions merge on the same name/comodel.
    team_id = fields.Many2one(
        "crm.team",
        string="Sales Team",
        help="Sales team of this invoice. Sales from the company's special "
        "sales teams (with a qualifying discount) have their royalties computed "
        "on the net invoiced amount.",
    )

    def action_generate_royalty_analytic_lines(self):
        """Generate royalty analytic lines from the selected paid invoices."""
        moves = self.filtered(
            lambda m: m.move_type == "out_invoice"
            and m.state == "posted"
            and m.payment_state in ("paid", "in_payment", "reversed")
        )
        templates = moves.invoice_line_ids.product_id.product_tmpl_id
        royalty_lines = self.env["edlab.contract.royalty.line"].search(
            [
                ("product_id", "in", templates.ids),
                ("analytic_account_id", "!=", False),
            ]
        )
        return royalty_lines._book_royalties_from_invoices(moves)
