# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # v19: analytic groups were replaced by analytic plans (account.analytic.plan).
    contract_analytic_group_id = fields.Many2one(
        "account.analytic.plan",
        string="Analytic Plan",
        help="Analytic plan under which the analytic accounts created from "
        "copyright contracts are placed.",
    )
    def _contract_analytic_plan(self):
        """O plano onde vivem os analíticos de direitos autorais.

        Cai no plano que o módulo traz ("Copyright Contracts") quando a empresa
        não escolheu outro. É o ÚNICO ponto que decide isso: tanto a criação das
        contas quanto o filtro do menu passam por aqui, senão as duas respostas
        divergem e o menu mostra um conjunto que não é o que ele criou.
        """
        self.ensure_one()
        if self.contract_analytic_group_id:
            return self.contract_analytic_group_id
        return self.env.ref(
            "liber_copyright_contracts_analytics.analytic_plan_copyright",
            raise_if_not_found=False,
        ) or self.env["account.analytic.plan"]

    contract_royalty_general_account_id = fields.Many2one(
        "account.account",
        string="Expense Account",
        domain="[('company_ids', 'in', id)]",
        help="Expense account recorded on royalty analytic lines while they are "
        "still within the operational window (not yet overdue as a liability).",
    )
    contract_royalty_liability_account_id = fields.Many2one(
        "account.account",
        string="Liability Account",
        domain="[('company_ids', 'in', id)]",
        help="Liability account used on royalty analytic lines that are overdue "
        "beyond the threshold below (no longer an operational expense).",
    )
    contract_royalty_liability_months = fields.Integer(
        string="Liability After (months)",
        default=20,
        help="A royalty overdue by more than this many months is reclassified "
        "from the expense account to the liability account. 0 disables it.",
    )
    contract_special_sales_team_ids = fields.Many2many(
        "crm.team",
        string="Special Sales Teams",
        help="Sales from these teams are treated as special sales: their "
        "royalties are always computed on the net invoiced amount (the "
        "invoice), never on the sales/cover price, no matter the royalty "
        "line's 'On Sales Price' setting. Requires the minimum discount below.",
    )
    contract_special_min_discount = fields.Float(
        string="Special Sales Min. Discount (%)",
        digits=(5, 2),
        help="Minimum invoice-line discount for a sale from the special sales "
        "team to count as a special sale (computed on the net amount). "
        "0 means any discount qualifies.",
    )
    special_sales_count = fields.Integer(
        string="Special Sales",
        compute="_compute_special_sales_count",
    )

    def _special_sales_domain(self):
        """Customer invoices that qualify as special sales: from a special
        sales team and with a line discount at/above the minimum."""
        self.ensure_one()
        teams = self.contract_special_sales_team_ids
        if not teams:
            return [("id", "=", False)]
        return [
            ("company_id", "=", self.id),
            ("move_type", "=", "out_invoice"),
            ("team_id", "in", teams.ids),
            ("invoice_line_ids.discount", ">=", self.contract_special_min_discount),
        ]

    @api.depends("contract_special_sales_team_ids", "contract_special_min_discount")
    def _compute_special_sales_count(self):
        Move = self.env["account.move"].sudo()
        for company in self:
            company.special_sales_count = Move.search_count(
                company._special_sales_domain()
            )

    def action_view_special_sales(self):
        """Open the customer invoices that qualify as special sales."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Special Sales"),
            "res_model": "account.move",
            "domain": self._special_sales_domain(),
            "view_mode": "list,form",
            "context": {"create": False, "default_move_type": "out_invoice"},
        }
