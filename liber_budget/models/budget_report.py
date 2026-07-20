# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class BudgetReport(models.Model):
    """View SQL de análise (pivot/graph): uma linha por budget.line, com
    Planned/Theoretical da linha e Programmed/Practical somados do Razão
    (modo GL) e dos analytic lines (modo analítico), na convenção P&L."""
    _name = 'budget.report'
    _description = "Budget Analysis"
    _auto = False
    _order = 'date_from desc, budget_analytic_id'

    budget_analytic_id = fields.Many2one('budget.analytic', string="Budget", readonly=True)
    budget_line_id = fields.Many2one('budget.line', string="Budget Line", readonly=True)
    group_id = fields.Many2one('budget.group', string="Group", readonly=True)
    position_id = fields.Many2one('budget.position', string="Budgetary Position", readonly=True)
    account_id = fields.Many2one('account.analytic.account', string="Analytic Account", readonly=True)
    company_id = fields.Many2one('res.company', string="Company", readonly=True)
    currency_id = fields.Many2one('res.currency', string="Currency", readonly=True)
    date_from = fields.Date(string="Start Date", readonly=True)
    date_to = fields.Date(string="End Date", readonly=True)
    planned = fields.Monetary(string="Planned", readonly=True)
    theoretical = fields.Monetary(string="Theoretical", readonly=True)
    programmed = fields.Monetary(string="Programmed", readonly=True)
    practical = fields.Monetary(string="Practical", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW %s AS (
                SELECT
                    bl.id                  AS id,
                    bl.id                  AS budget_line_id,
                    bl.budget_analytic_id  AS budget_analytic_id,
                    ba.group_id            AS group_id,
                    bl.position_id         AS position_id,
                    bl.account_id          AS account_id,
                    bl.company_id          AS company_id,
                    comp.currency_id       AS currency_id,
                    bl.date_from           AS date_from,
                    bl.date_to             AS date_to,
                    bl.budget_amount       AS planned,
                    CASE
                        WHEN CURRENT_DATE < bl.date_from THEN 0
                        WHEN CURRENT_DATE > bl.date_to   THEN bl.budget_amount
                        ELSE bl.budget_amount * (
                            (CURRENT_DATE - bl.date_from + 1)::float
                            / NULLIF(bl.date_to - bl.date_from + 1, 0)
                        )
                    END                    AS theoretical,
                    COALESCE(gl.programmed, 0) + COALESCE(aa.programmed, 0) AS programmed,
                    COALESCE(gl.practical, 0)  + COALESCE(aa.practical, 0)  AS practical
                FROM budget_line bl
                JOIN budget_analytic ba   ON ba.id = bl.budget_analytic_id
                JOIN res_company comp      ON comp.id = bl.company_id
                -- modo GL (posição orçamentária): P&L => practical = -balance
                LEFT JOIN LATERAL (
                    SELECT
                        -SUM(aml.balance) FILTER (WHERE aml.parent_state = 'posted') AS practical,
                        -SUM(aml.balance) AS programmed
                    FROM account_move_line aml
                    JOIN account_account_budget_position_rel rel
                        ON rel.account_account_id = aml.account_id
                    WHERE bl.position_id IS NOT NULL
                      AND rel.budget_position_id = bl.position_id
                      AND aml.company_id = bl.company_id
                      AND aml.date BETWEEN bl.date_from AND bl.date_to
                      AND aml.parent_state IN ('draft', 'posted')
                ) gl ON TRUE
                -- modo analítico: P&L => practical = +amount (1 plano: account_id)
                LEFT JOIN LATERAL (
                    SELECT
                        SUM(aal.amount) FILTER (
                            WHERE aal.move_line_id IS NULL OR ml.parent_state = 'posted'
                        ) AS practical,
                        SUM(aal.amount) AS programmed
                    FROM account_analytic_line aal
                    LEFT JOIN account_move_line ml ON ml.id = aal.move_line_id
                    WHERE bl.position_id IS NULL
                      AND bl.account_id IS NOT NULL
                      AND aal.account_id = bl.account_id
                      AND aal.company_id = bl.company_id
                      AND aal.date BETWEEN bl.date_from AND bl.date_to
                      AND (aal.move_line_id IS NULL OR ml.parent_state IN ('draft', 'posted'))
                ) aa ON TRUE
            )
        """ % (self._table,))
