# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BudgetLine(models.Model):
    _name = 'budget.line'
    _inherit = ['analytic.plan.fields.mixin']
    _description = "Budget Line"
    _order = 'sequence, id'

    budget_analytic_id = fields.Many2one(
        'budget.analytic', string="Budget",
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    position_id = fields.Many2one(
        'budget.position', string="Budgetary Position",
        help="If set, actuals come from the General Ledger accounts of this "
             "position (works retroactively). Otherwise, from analytic lines.")
    company_id = fields.Many2one(
        related='budget_analytic_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')
    date_from = fields.Date(
        related='budget_analytic_id.date_from', store=True, readonly=True)
    date_to = fields.Date(
        related='budget_analytic_id.date_to', store=True, readonly=True)

    # --- amounts ---------------------------------------------------------
    budget_amount = fields.Monetary(string="Planned")                       # Previsto
    theoritical_amount = fields.Monetary(
        string="Theoretical", compute='_compute_theoritical')               # Teórico
    practical_amount = fields.Monetary(
        string="Practical", compute='_compute_actuals',
        help="Realized amount from POSTED entries (and manual analytic lines).")  # Prático
    programmed_amount = fields.Monetary(
        string="Programmed", compute='_compute_actuals',
        help="All entered journal items in the period (DRAFT + POSTED). "
             "Includes the practical amount.")                              # Programado
    practical_percentage = fields.Float(
        string="Practical (%)", compute='_compute_actuals')
    theoritical_percentage = fields.Float(
        string="Theoretical (%)", compute='_compute_theoritical')

    # --- computes --------------------------------------------------------
    @api.depends('company_id')
    def _compute_currency_id(self):
        for line in self:
            line.currency_id = (line.company_id or self.env.company).currency_id

    @api.depends('budget_amount', 'date_from', 'date_to')
    def _compute_theoritical(self):
        today = fields.Date.context_today(self)
        for line in self:
            if not line.date_from or not line.date_to:
                line.theoritical_amount = 0.0
                line.theoritical_percentage = 0.0
                continue
            total_days = (line.date_to - line.date_from).days + 1
            clamped = min(max(today, line.date_from), line.date_to)
            elapsed_days = (clamped - line.date_from).days + 1
            ratio = (elapsed_days / total_days) if total_days else 0.0
            line.theoritical_amount = line.budget_amount * ratio
            line.theoritical_percentage = (
                line.theoritical_amount / line.budget_amount) if line.budget_amount else 0.0

    def _actuals_account_terms(self):
        """Domain terms matching the analytic account(s) chosen on this line,
        across every analytic plan column that is set (single- or multi-plan)."""
        self.ensure_one()
        terms = []
        for fname in self._get_plan_fnames():
            if self[fname]:
                terms.append((fname, '=', self[fname].id))
        return terms

    @api.depends('position_id', 'budget_amount', 'date_from', 'date_to')
    def _compute_actuals(self):
        for line in self:
            line.practical_amount = 0.0
            line.programmed_amount = 0.0
            line.practical_percentage = 0.0
            if not (line.date_from and line.date_to):
                continue
            if line.position_id:
                practical, programmed = line._gl_actuals()        # modo GL (retroativo)
            else:
                practical, programmed = line._analytic_actuals()  # modo analitico
            line.practical_amount = practical
            line.programmed_amount = programmed
            line.practical_percentage = (
                line.practical_amount / line.budget_amount) if line.budget_amount else 0.0

    @staticmethod
    def _sum_read_group(result):
        return result[0][0] if result and result[0][0] is not None else 0.0

    # Convencao de RESULTADO (P&L): receita +, despesa -, total = resultado liquido.
    def _analytic_actuals(self):
        """Practical/Programmed a partir dos analytic lines (precisa de tag analitica)."""
        self.ensure_one()
        account_terms = self._actuals_account_terms()
        if not account_terms:
            return 0.0, 0.0
        return (
            self._analytic_signed_sum(account_terms, ('posted',)),
            self._analytic_signed_sum(account_terms, ('draft', 'posted')),
        )

    def _analytic_signed_sum(self, account_terms, states):
        AAL = self.env['account.analytic.line'].sudo()
        base = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ] + account_terms + [
            '|', ('move_line_id', '=', False),
            ('move_line_id.parent_state', 'in', states),
        ]
        # analytic 'amount' ja vem na convencao P&L (despesa -, receita +)
        res = AAL._read_group(base, [], ['amount:sum'])
        return self._sum_read_group(res)

    def _gl_actuals(self):
        """Practical/Programmed a partir do Razao (account.move.line) nas contas da
        posicao. Funciona retroativo, sem preparo."""
        self.ensure_one()
        accounts = self.position_id.account_ids
        if not accounts:
            return 0.0, 0.0
        return (
            self._gl_signed_sum(accounts, ('posted',)),
            self._gl_signed_sum(accounts, ('draft', 'posted')),
        )

    def _gl_signed_sum(self, accounts, states):
        AML = self.env['account.move.line'].sudo()
        base = [
            ('account_id', 'in', accounts.ids),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('parent_state', 'in', states),
        ]
        # balance = debito - credito (despesa +, receita -) -> negamos p/ convencao P&L
        res = AML._read_group(base, [], ['balance:sum'])
        return -self._sum_read_group(res)

    @api.constrains(lambda self: self._get_plan_fnames() + ['position_id', 'budget_analytic_id'])
    def _check_account_id(self):
        """Override the core mixin rule: the analytic account is OPTIONAL here.
        A line just needs a source of actuals -> either a Budgetary Position (GL)
        or at least one analytic account."""
        for line in self:
            if line.position_id:
                continue
            if not any(line[fname] for fname in line._get_plan_fnames()):
                raise ValidationError(_(
                    "Set a Budgetary Position or at least one analytic account "
                    "on the budget line."))

    def action_open_entries(self):
        """Abre os lancamentos (Journal Items / Analytic Items) desta linha."""
        self.ensure_one()
        domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
        ]
        if self.position_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _("Journal Items"),
                'res_model': 'account.move.line',
                'view_mode': 'list,form',
                'domain': domain + [
                    ('account_id', 'in', self.position_id.account_ids.ids),
                    ('parent_state', 'in', ('draft', 'posted')),
                ],
                'context': {'search_default_group_by_account': 1},
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _("Analytic Items"),
            'res_model': 'account.analytic.line',
            'view_mode': 'list,form',
            'domain': domain + self._actuals_account_terms(),
        }
