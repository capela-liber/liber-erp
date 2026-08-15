# -*- coding: utf-8 -*-
from ast import literal_eval

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBudgetPnlReport(TransactionCase):
    """A view SQL do P&L: sinal, seção, grupo por prefixo e recorte de acesso."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Pnl = cls.env['budget.pnl.report']

        def conta(name, code, account_type):
            return cls.env['account.account'].create({
                'name': name, 'code': code, 'account_type': account_type,
                'company_ids': [Command.link(cls.company.id)],
            })

        # códigos com prefixo comum de propósito: alimentam o teste de grupo
        cls.acc_income = conta('PnL Receita', 'PNL3100', 'income')
        cls.acc_income_other = conta('PnL Outras Receitas', 'PNL3900', 'income_other')
        cls.acc_cost = conta('PnL Custo', 'PNL4100', 'expense_direct_cost')
        cls.acc_expense = conta('PnL Despesa', 'PNL5100', 'expense')
        cls.acc_cash = conta('PnL Caixa', 'PNL1100', 'asset_cash')

        cls.journal = cls.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', cls.company.id)], limit=1)

    # ------------------------------------------------------------------
    def _move(self, account, debit, credit, date='2026-03-15', post=True):
        """Lançamento de uma perna na conta de resultado e a contrapartida no caixa."""
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': date,
            'line_ids': [
                Command.create({
                    'account_id': account.id, 'debit': debit, 'credit': credit}),
                Command.create({
                    'account_id': self.acc_cash.id, 'debit': credit, 'credit': debit}),
            ],
        })
        if post:
            move.action_post()
        return move

    def _rows(self, account):
        # a view SQL lê account_move_line direto: o ORM não sabe que precisa
        # descarregar o cache dessa tabela antes do SELECT
        self.env.flush_all()
        return self.Pnl.search([('account_id', '=', account.id)])

    # --- caminho feliz --------------------------------------------------
    def test_sign_and_account_type(self):
        """Receita entra +, custo e despesa entram -, cada uma no seu tipo."""
        self._move(self.acc_income, debit=0, credit=1000)          # receita
        self._move(self.acc_cost, debit=400, credit=0)             # custo
        self._move(self.acc_expense, debit=250, credit=0)          # despesa
        self._move(self.acc_income_other, debit=0, credit=50)      # outra receita

        receita = self._rows(self.acc_income)
        self.assertEqual(len(receita), 1)
        self.assertAlmostEqual(receita.amount, 1000.0, places=2)
        self.assertEqual(receita.account_type, '1_income')

        custo = self._rows(self.acc_cost)
        self.assertAlmostEqual(custo.amount, -400.0, places=2)
        self.assertEqual(custo.account_type, '3_expense_direct_cost')

        despesa = self._rows(self.acc_expense)
        self.assertAlmostEqual(despesa.amount, -250.0, places=2)
        self.assertEqual(despesa.account_type, '4_expense')

        # cada tipo tem a sua linha: "Outras Receitas" não some dentro de Receita
        self.assertEqual(
            self._rows(self.acc_income_other).account_type, '2_income_other')

    def test_labels_come_from_odoo(self):
        """Os rótulos são os do core -- não uma segunda nomenclatura da casa."""
        rotulos = dict(self.Pnl.fields_get(['account_type'])['account_type']['selection'])
        do_core = dict(self.env['account.account'].fields_get(
            ['account_type'])['account_type']['selection'])
        for meu, cru in [('1_income', 'income'),
                         ('3_expense_direct_cost', 'expense_direct_cost'),
                         ('6_expense_depreciation', 'expense_depreciation')]:
            self.assertEqual(rotulos[meu], do_core[cru])
        # e são só os seis de resultado, nenhum de balanço
        self.assertEqual(len(rotulos), 6)

    def test_three_filters_split_the_statement(self):
        """As três filtragens recortam os seis tipos sem sobra nem repetição.

        Os domínios saem do arch da busca, não repetidos aqui: assim o teste
        guarda as filtragens que a tela realmente usa, e não uma cópia delas.
        """
        self._move(self.acc_income, debit=0, credit=1000)
        self._move(self.acc_income_other, debit=0, credit=50)
        self._move(self.acc_cost, debit=400, credit=0)
        self._move(self.acc_expense, debit=250, credit=0)
        contas = (self.acc_income + self.acc_income_other
                  + self.acc_cost + self.acc_expense)
        self.env.flush_all()

        arch = etree.fromstring(self.Pnl.get_view(
            self.env.ref('liber_budget.pnl_report_view_search').id, 'search')['arch'])
        dominios = {
            no.get('name'): literal_eval(no.get('domain'))
            for no in arch.findall('.//filter[@domain]')
            if no.get('name') in ('income', 'cost_of_revenue', 'expense')
        }
        self.assertEqual(set(dominios), {'income', 'cost_of_revenue', 'expense'})

        def soma(nome):
            return sum(self.Pnl.search(
                [('account_id', 'in', contas.ids)] + dominios[nome]).mapped('amount'))

        self.assertAlmostEqual(soma('income'), 1050.0, places=2)
        self.assertAlmostEqual(soma('cost_of_revenue'), -400.0, places=2)
        self.assertAlmostEqual(soma('expense'), -250.0, places=2)
        # as três somadas dão o total: nenhum tipo ficou de fora nem entrou duas vezes
        total = sum(self.Pnl.search(
            [('account_id', 'in', contas.ids)]).mapped('amount'))
        self.assertAlmostEqual(
            soma('income') + soma('cost_of_revenue') + soma('expense'),
            total, places=2)
        self.assertAlmostEqual(total, 400.0, places=2)

        # o total das quatro é o resultado do período
        total = sum(
            self.Pnl.search([
                ('account_id', 'in', (
                    self.acc_income + self.acc_income_other
                    + self.acc_cost + self.acc_expense).ids),
            ]).mapped('amount'))
        self.assertAlmostEqual(total, 400.0, places=2)  # 1000 + 50 - 400 - 250

    def test_balance_sheet_accounts_are_out(self):
        """Conta patrimonial nunca aparece: o demonstrativo é só de resultado."""
        self._move(self.acc_expense, debit=100, credit=0)
        self.assertFalse(self._rows(self.acc_cash))

    def test_account_group_by_code_prefix(self):
        """O grupo vem do prefixo do código -- é o desdobramento pelo plano de contas.

        `account_account.group_id` é compute sem store; a view refaz a regra em
        SQL, então este teste é o que garante que ela continua igual à do core.
        """
        raiz = self.company.root_id
        grupo = self.env['account.group'].create({
            'name': 'PnL Grupo 41', 'code_prefix_start': 'PNL41',
            'code_prefix_end': 'PNL41', 'company_id': raiz.id,
        })
        # prefixo mais longo ganha do mais curto, como no core
        largo = self.env['account.group'].create({
            'name': 'PnL Grupo 4', 'code_prefix_start': 'PNL4',
            'code_prefix_end': 'PNL4', 'company_id': raiz.id,
        })
        self._move(self.acc_cost, debit=400, credit=0)

        # a view é materializada na instalação: reconstrói para ver os grupos novos
        self.Pnl.init()
        linha = self._rows(self.acc_cost)
        self.assertEqual(linha.group_id, grupo)
        self.assertEqual(linha.code, 'PNL4100')
        self.assertNotEqual(linha.group_id, largo)

    # --- edge cases -----------------------------------------------------
    def test_draft_is_visible_cancelled_is_not(self):
        """Rascunho aparece marcado como draft; cancelado some da view."""
        rascunho = self._move(self.acc_expense, debit=100, credit=0, post=False)
        linha = self._rows(self.acc_expense)
        self.assertEqual(linha.state, 'draft')
        self.assertAlmostEqual(linha.amount, -100.0, places=2)

        rascunho.button_cancel()
        self.assertFalse(self._rows(self.acc_expense))

    def test_grouping_orders_income_first(self):
        """O demonstrativo abre de cima para baixo: receita, custo, despesa.

        Este é o teste que justifica o prefixo numérico no valor. O pivot ordena
        os grupos pela coluna do GROUP BY; com os valores crus do Odoo,
        'expense' viria antes de 'income' e a tela abriria invertida.
        """
        self._move(self.acc_income, debit=0, credit=1000)
        self._move(self.acc_cost, debit=400, credit=0)
        self._move(self.acc_expense, debit=250, credit=0)

        self.env.flush_all()
        grupos = self.Pnl._read_group(
            [('account_id', 'in', (
                self.acc_income + self.acc_cost + self.acc_expense).ids)],
            ['account_type'], ['amount:sum'])
        self.assertEqual(
            [g[0] for g in grupos],
            ['1_income', '3_expense_direct_cost', '4_expense'])
        self.assertAlmostEqual(grupos[0][1], 1000.0, places=2)
        self.assertAlmostEqual(grupos[1][1], -400.0, places=2)
        self.assertAlmostEqual(grupos[2][1], -250.0, places=2)

        # e é a mesma ordem que a tela recebe, não só o _read_group cru
        pela_tela = self.Pnl.web_read_group(
            [('account_id', 'in', (
                self.acc_income + self.acc_cost + self.acc_expense).ids)],
            ['account_type'], ['amount:sum'])
        self.assertEqual(
            [g['account_type'] for g in pela_tela['groups']],
            ['1_income', '3_expense_direct_cost', '4_expense'])

    # --- caso de erro ---------------------------------------------------
    def test_read_requires_budget_group(self):
        """Fora do grupo Budget não se lê o resultado da casa."""
        self._move(self.acc_income, debit=0, credit=1000)
        forasteiro = self.env['res.users'].create({
            'name': 'PnL Forasteiro', 'login': 'pnl_forasteiro',
            'group_ids': [Command.set(self.env.ref('base.group_user').ids)],
        })
        with self.assertRaises(AccessError):
            self.Pnl.with_user(forasteiro).search([])
