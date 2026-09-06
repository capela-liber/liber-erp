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


    # ------------------------------------------------- orçamento consolidado

    def _outra_empresa(self):
        """Uma segunda empresa do banco, com diário geral e conta própria.

        Não se cria `res.company` aqui de propósito: com o `account`
        instalado, o create estoura em NOT NULL de `fiscalyear_last_day`.
        Reaproveita-se o que o banco tem — regra da casa.
        """
        outra = self.env['res.company'].search(
            [('id', '!=', self.company.id)], limit=1)
        if not outra:
            return None, None, None
        diario = self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', outra.id)], limit=1)
        if not diario:
            return None, None, None
        desp = self.env['account.account'].create({
            'name': 'LabBudget Outra Expense', 'code': 'LBTE2',
            'account_type': 'expense',
            'company_ids': [Command.link(outra.id)],
        })
        caixa = self.env['account.account'].create({
            'name': 'LabBudget Outra Cash', 'code': 'LBTC2',
            'account_type': 'asset_cash',
            'company_ids': [Command.link(outra.id)],
        })
        move = self.env['account.move'].with_company(outra).create({
            'move_type': 'entry', 'journal_id': diario.id, 'date': '2020-06-01',
            'line_ids': [
                Command.create({'account_id': desp.id, 'debit': 700, 'credit': 0}),
                Command.create({'account_id': caixa.id, 'debit': 0, 'credit': 700}),
            ],
        })
        move.action_post()
        return outra, desp, move

    def test_consolidado_soma_a_outra_empresa(self):
        """Com `company_ids`, o practical passa a somar as filhas.

        É o conserto de 31/08: a casa monta orçamentos "EL+HE" e "SA+LO" na
        holding, e o practical dava ZERO em 114 linhas porque o realizado era
        procurado só nos livros de quem assina o orçamento. A via natural —
        pôr a holding como empresa-pai — está FECHADA pelo Odoo
        (`res_company.write` recusa mudar a hierarquia, e no 19 `parent_id`
        significa filial, não controlada).
        """
        outra, desp_outra, _mv = self._outra_empresa()
        if not outra:
            self.skipTest('este banco tem uma empresa só')

        posicao = self.env['budget.position'].create({
            'name': 'LabBudget Pos Consolidada',
            'account_ids': [Command.set((self.exp_account | desp_outra).ids)],
        })
        self._move(300, '2020-06-01', post=True)     # 300 na própria empresa

        b = self._budget()
        linha = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': posicao.id,
            'budget_amount': -1000,
            'date_from': b.date_from, 'date_to': b.date_to,
        })

        # sem a lista: só a própria empresa (convenção P&L: despesa negativa)
        self.assertAlmostEqual(linha.practical_amount, -300, 2,
                               'sem consolidação, soma só a própria empresa')

        # com a lista: a própria entra sozinha, basta somar a OUTRA
        b.company_ids = [Command.set(outra.ids)]
        linha.invalidate_recordset(['practical_amount'])
        self.assertAlmostEqual(linha.practical_amount, -1000, 2,
                               'consolidado tem de somar as duas empresas')

    def test_a_propria_empresa_entra_sem_ser_listada(self):
        """A lista é "ALÉM da própria" -- o dono nunca precisa ser repetido.

        Preferência da casa em 31/08: quem monta um "EL+HE" na holding quer
        dizer "além de mim, some EL e HE", não "some EP, EL e HE".
        """
        outra = self.env['res.company'].search(
            [('id', '!=', self.company.id)], limit=1)
        if not outra:
            self.skipTest('este banco tem uma empresa só')
        b = self._budget()
        b.company_ids = [Command.set(outra.ids)]
        empresas = b._companies_for_actuals()
        self.assertIn(self.company, empresas,
                      'a própria empresa entra sem ser listada')
        self.assertIn(outra, empresas)

    def test_relatorio_acompanha_a_consolidacao(self):
        """A view SQL tem de dar o mesmo número que o compute da linha."""
        outra, desp_outra, _mv = self._outra_empresa()
        if not outra:
            self.skipTest('este banco tem uma empresa só')
        posicao = self.env['budget.position'].create({
            'name': 'LabBudget Pos Rel', 'account_ids': [Command.set(desp_outra.ids)]})
        b = self._budget()
        b.company_ids = [Command.set(outra.ids)]
        linha = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': posicao.id,
            'budget_amount': -1000,
            'date_from': b.date_from, 'date_to': b.date_to,
        })
        self.env.flush_all()
        rel = self.env['budget.report'].search([('budget_line_id', '=', linha.id)])
        self.assertTrue(rel, 'a linha tem de aparecer no relatório')
        self.assertAlmostEqual(rel.practical, linha.practical_amount, 2,
                               'relatório e linha têm de dar o mesmo número')


@tagged('post_install', '-at_install')
class TestColunasDePlano(TransactionCase):
    """A view não pode presumir que o plano da casa é o de projetos.

    No 19, `analytic/models/analytic_plan.py` reserva a coluna `account_id` ao
    plano de projetos e dá `x_plan{id}_id` a todos os outros. O `budget_report`
    presumia `account_id`: num banco onde o plano da casa não é o de projetos a
    coluna não existe, a view não é criada e o upgrade do módulo morre com
    `Failed to load registry` -- levando junto o `practical_amount`.
    Aconteceu no banco da migração Hedra em 31/07/2026, com `x_plan3_id`.
    """

    def test_colunas_saem_do_odoo_e_existem_na_tabela(self):
        colunas = self.env['budget.report']._colunas_de_plano()
        self.assertTrue(colunas, "sempre há ao menos uma coluna de plano")

        planos = self.env['account.analytic.plan'].sudo().search(
            [('parent_id', '=', False)])
        esperadas = {p._column_name() for p in planos}
        self.assertTrue(set(colunas) <= esperadas,
                        "nenhuma coluna inventada: todas vêm de um plano raiz")

        self.env.cr.execute("""
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'account_analytic_line'
        """)
        na_tabela = {r[0] for r in self.env.cr.fetchall()}
        self.assertTrue(set(colunas) <= na_tabela,
                        "só entra coluna que existe de fato — plano pode existir "
                        "sem a coluna materializada")

    def test_um_plano_novo_entra_na_juncao(self):
        plano = self.env['account.analytic.plan'].create({'name': 'Plano do teste'})
        coluna = plano._column_name()
        self.env.cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'account_analytic_line' AND column_name = %s
        """, (coluna,))
        if not self.env.cr.fetchone():
            self.skipTest("a coluna do plano novo ainda não foi materializada")
        self.assertIn(coluna, self.env['budget.report']._colunas_de_plano(),
                      "plano raiz novo tem de entrar na junção da view")
