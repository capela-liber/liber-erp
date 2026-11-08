# -*- coding: utf-8 -*-
"""Os caixas de feira, ao lado das outras decisões de Eventos.

Ver `res_company.py`: as contas são da empresa, e cada caixa novo nasce com
um diário de dinheiro próprio que as usa.
"""
from odoo import _, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fair_cash_account_id = fields.Many2one(
        related='company_id.fair_cash_account_id', readonly=False)
    fair_cash_surplus_account_id = fields.Many2one(
        related='company_id.default_cash_difference_income_account_id',
        readonly=False)
    fair_cash_shortage_account_id = fields.Many2one(
        related='company_id.default_cash_difference_expense_account_id',
        readonly=False)
    # Transitória e a receber do PDV são campos do núcleo, como sobra e
    # falta: ver `res_company.py`.
    fair_transit_account_id = fields.Many2one(
        related='company_id.account_journal_suspense_account_id',
        readonly=False)
    fair_pos_receivable_account_id = fields.Many2one(
        related='company_id.account_default_pos_receivable_account_id',
        readonly=False)
    fair_income_account_id = fields.Many2one(
        related='company_id.fair_income_account_id', readonly=False)
    fair_payment_method_ids = fields.Many2many(
        related='company_id.fair_payment_method_ids', readonly=False)

    def set_values(self):
        super().set_values()
        # O caixa que nasceu antes da configuração -- o primeiro da n-1,
        # 30/10/2026 -- não abriria nunca sem isto.
        self.company_id._fair_fill_cash_journals()
        self.company_id._fair_ensure_drawer()

    def action_fair_drawers(self):
        """Os diários das gavetas desta empresa, para ajustar à mão."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fair cash drawers'),
            'res_model': 'account.journal',
            'view_mode': 'list,form',
            'domain': [('id', 'in',
                        self.company_id._fair_drawers().journal_id.ids)],
        }
