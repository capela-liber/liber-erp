# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLabBudget(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # contas GL frescas (isoladas de qualquer lançamento existente)
        cls.exp_account = cls.env['account.account'].create({
            'name': 'LabBudget Test Expense', 'code': 'LBTE',
            'account_type': 'expense',
            'company_ids': [Command.link(cls.company.id)],
        })
        cls.cash_account = cls.env['account.account'].create({
            'name': 'LabBudget Test Cash', 'code': 'LBTC',
            'account_type': 'asset_cash',
            'company_ids': [Command.link(cls.company.id)],
        })
        cls.journal = cls.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', cls.company.id)], limit=1)
        # analítica fresca
        cls.plan = cls.env['account.analytic.plan'].create({'name': 'LabBudget Plan'})
        cls.analytic = cls.env['account.analytic.account'].create({
            'name': 'LabBudget Proj', 'plan_id': cls.plan.id})
        # posição orçamentária (modo GL) com a conta de despesa fresca
        cls.position = cls.env['budget.position'].create({
            'name': 'LabBudget Pos',
            'account_ids': [Command.set(cls.exp_account.ids)],
        })

    def _budget(self, date_from='2020-01-01', date_to='2020-12-31'):
        return self.env['budget.analytic'].create({
            'name': 'B Test', 'date_from': date_from, 'date_to': date_to})

    def _move(self, amount, date, post):
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': date,
            'line_ids': [
                Command.create({'account_id': self.exp_account.id, 'debit': amount, 'credit': 0}),
                Command.create({'account_id': self.cash_account.id, 'debit': 0, 'credit': amount}),
            ],
        })
        if post:
            move.action_post()
        return move

    # ------------------------------------------------------------------
    def test_states_and_revision(self):
        b = self._budget()
        self.assertEqual(b.state, 'draft')
        b.action_confirm()
        self.assertEqual(b.state, 'confirmed')
        b.action_create_revision()
        self.assertEqual(b.state, 'revised')
        self.assertEqual(len(b.children_ids), 1)
        self.assertEqual(b.children_ids.parent_id, b)

    def test_theoretical_past_is_full(self):
        # janela 100% no passado -> Teórico == Previsto
        b = self._budget('2020-01-01', '2020-12-31')
        line = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})
        self.assertAlmostEqual(line.theoritical_amount, -1000, places=2)

    def test_gl_practical_programmed_pnl_sign(self):
        b = self._budget()
        line = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})
        self._move(1000, '2020-06-01', post=True)    # despesa posted -> balance +1000
        self._move(300, '2020-06-02', post=False)    # despesa draft
        line.invalidate_recordset()
        # P&L: practical = -balance(posted) = -1000
        self.assertAlmostEqual(line.practical_amount, -1000, places=2)
        # programmed = -(posted + draft) = -1300
        self.assertAlmostEqual(line.programmed_amount, -1300, places=2)

    def test_analytic_practical_pnl_sign(self):
        b = self._budget()
        line = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'account_id': self.analytic.id,
            'budget_amount': -500})
        self.env['account.analytic.line'].create({
            'name': 'cost', 'account_id': self.analytic.id,
            'amount': -500, 'date': '2020-06-01'})
        line.invalidate_recordset()
        # analítico P&L: practical = +amount = -500
        self.assertAlmostEqual(line.practical_amount, -500, places=2)

    def test_line_requires_source(self):
        b = self._budget()
        with self.assertRaises(ValidationError):
            self.env['budget.line'].create({
                'budget_analytic_id': b.id, 'budget_amount': -100})

    def test_report_matches_line(self):
        b = self._budget()
        line = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})
        self._move(1000, '2020-06-01', post=True)
        self.env.flush_all()  # garante que os lançamentos estão no banco p/ a view SQL
        line.invalidate_recordset()
        rep = self.env['budget.report'].search([('budget_line_id', '=', line.id)])
        self.assertEqual(len(rep), 1)
        self.assertAlmostEqual(rep.practical, line.practical_amount, places=2)
        self.assertAlmostEqual(rep.planned, -1000, places=2)
