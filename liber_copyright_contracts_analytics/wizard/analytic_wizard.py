# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AnalyticWizard(models.TransientModel):
    _name = "edlab.contract.analytic.wizard"
    _description = "Create Analytic Accounts for Contract Beneficiaries"

    contract_id = fields.Many2one(
        "edlab.contract",
        string="Contract",
        required=True,
        ondelete="cascade",
    )
    line_ids = fields.One2many(
        "edlab.contract.analytic.wizard.line",
        "wizard_id",
        string="Beneficiaries",
    )

    def action_confirm(self):
        self.ensure_one()
        apply_lines = self.line_ids.filtered("to_apply")
        # lines where the user picked an existing account -> just link it
        chosen = apply_lines.filtered("analytic_account_id")
        for wline in chosen:
            wline.royalty_line_id.analytic_account_id = wline.analytic_account_id
        # remaining lines -> create a new account with the standard name
        to_generate = (apply_lines - chosen).mapped("royalty_line_id")
        if to_generate:
            to_generate.action_create_analytic_account()
        return {"type": "ir.actions.act_window_close"}


class AnalyticWizardLine(models.TransientModel):
    _name = "edlab.contract.analytic.wizard.line"
    _description = "Create Analytic Accounts - Beneficiary Line"

    wizard_id = fields.Many2one(
        "edlab.contract.analytic.wizard",
        required=True,
        ondelete="cascade",
    )
    royalty_line_id = fields.Many2one(
        "edlab.contract.royalty.line",
        string="Royalty Line",
        required=True,
    )
    partner_id = fields.Many2one(
        related="royalty_line_id.partner_id",
        string="Beneficiary",
    )
    product_id = fields.Many2one(
        related="royalty_line_id.product_id",
        string="Work",
    )
    analytic_name = fields.Char(
        related="royalty_line_id.analytic_name",
        string="New Account Name",
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        help="Leave empty to create a new account with the suggested name, "
        "or pick an existing account to link instead.",
    )
    to_apply = fields.Boolean(string="Apply", default=True)

    @api.onchange("analytic_account_id")
    def _onchange_analytic_account_id(self):
        if self.analytic_account_id:
            self.to_apply = True
