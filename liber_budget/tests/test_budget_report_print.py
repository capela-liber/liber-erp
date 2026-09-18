# -*- coding: utf-8 -*-
"""O botão "Imprimir" que faltava na tela.

O menu Ações do orçamento só tinha Duplicar/Excluir -- sem opção de PDF. O
que se prova aqui é o que a tela precisa: o report aparece ligado ao modelo
(a tela oferece o botão) e o PDF sai de verdade, com e sem linha.
"""
import re

from odoo import Command
from odoo.tests import TransactionCase, tagged

REPORT = 'liber_budget.report_budget_analytic'


@tagged('post_install', '-at_install')
class TestBudgetReportPrint(TransactionCase):
    """`force_report_rendering=True`: sem isso o Odoo, em modo de teste,
    devolve o HTML em vez de rodar o wkhtmltopdf (atalho do próprio core em
    `_pre_render_qweb_pdf`, para não pagar o custo do PDF em toda suíte) --
    e o que se quer provar aqui é justamente o PDF."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.exp_account = cls.env['account.account'].create({
            'name': 'LabBudgetPrint Expense', 'code': 'LBPE',
            'account_type': 'expense',
            'company_ids': [Command.link(cls.company.id)],
        })
        cls.position = cls.env['budget.position'].create({
            'name': 'LabBudgetPrint Pos',
            'account_ids': [Command.set(cls.exp_account.ids)],
        })
        cls.plan = cls.env['account.analytic.plan'].create({'name': 'LabBudgetPrint Plan'})
        cls.analytic = cls.env['account.analytic.account'].create({
            'name': 'LabBudgetPrint Proj', 'plan_id': cls.plan.id})
        cls.cash_account = cls.env['account.account'].create({
            'name': 'LabBudgetPrint Cash', 'code': 'LBPC',
            'account_type': 'asset_cash',
            'company_ids': [Command.link(cls.company.id)],
        })
        cls.journal = cls.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', cls.company.id)], limit=1)

    def _budget(self, date_from='2020-01-01', date_to='2020-12-31'):
        return self.env['budget.analytic'].create({
            'name': 'B Print Test', 'date_from': date_from, 'date_to': date_to})

    def test_orcamento_com_linhas_gera_pdf(self):
        """Caminho feliz: orçamento com linha de posição e linha analítica."""
        b = self._budget()
        self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})
        self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'account_id': self.analytic.id,
            'budget_amount': -500})

        pdf, tipo = self.env['ir.actions.report'].with_context(
            force_report_rendering=True)._render_qweb_pdf(REPORT, res_ids=[b.id])

        self.assertEqual(tipo, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'), "o retorno tem de ser um PDF de verdade")
        self.assertGreater(len(pdf), 1000, "um orçamento de uma página tem alguns KB")

    def test_orcamento_sem_linhas_nao_quebra(self):
        """Edge case: orçamento recém-criado, sem nenhuma linha ainda."""
        b = self._budget()

        pdf, tipo = self.env['ir.actions.report'].with_context(
            force_report_rendering=True)._render_qweb_pdf(REPORT, res_ids=[b.id])

        self.assertEqual(tipo, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_impressao_aparece_ligada_ao_modelo(self):
        """É isso que faz o botão de imprimir aparecer na tela do orçamento --
        sem `binding_model_id` o menu Ações continua só com Duplicar/Excluir."""
        action = self.env.ref('liber_budget.action_report_budget_analytic')
        self.assertEqual(action.model, 'budget.analytic')
        self.assertEqual(action.binding_model_id.model, 'budget.analytic')
        self.assertEqual(action.binding_type, 'report')

    def test_papel_e_paisagem(self):
        """A tabela tem 6 colunas -- retrato apertava os valores."""
        action = self.env.ref('liber_budget.action_report_budget_analytic')
        self.assertEqual(action.paperformat_id.orientation, 'Landscape')

    def test_segunda_secao_lista_a_conta_da_posicao(self):
        """Caminho feliz da seção 2: a posição vira cabeçalho, e a conta do
        razão que a compõe entra como sub -- é a rastreabilidade que se pediu."""
        b = self._budget()
        self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})

        html, tipo = self.env['ir.actions.report']._render_qweb_html(REPORT, [b.id])
        html = html.decode()

        self.assertEqual(tipo, 'html')
        self.assertIn('Posições orçamentárias', html)
        self.assertIn(self.position.name, html)
        self.assertIn(self.exp_account.code, html)
        self.assertIn(self.exp_account.name, html)

    def test_posicao_sem_conta_avisa_em_vez_de_ficar_em_branco(self):
        """Edge case: posição sem nenhuma conta do razão configurada."""
        posicao_vazia = self.env['budget.position'].create({'name': 'LabBudgetPrint Pos Vazia'})
        b = self._budget()
        self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': posicao_vazia.id,
            'budget_amount': -1000})

        html, _tipo = self.env['ir.actions.report']._render_qweb_html(REPORT, [b.id])
        html = html.decode()

        self.assertIn(posicao_vazia.name, html)
        self.assertIn('Sem contas do razão configuradas.', html)

    def test_pratico_percent_sai_formatado_nao_cru(self):
        """Regressão: o widget 'percentage' não existe no QWeb de relatório
        (só no cliente web) -- t-field imprimia o float cru, tipo
        '0.9117149725', em vez de '91.17%'."""
        b = self._budget()
        line = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': '2020-06-01',
            'line_ids': [
                Command.create({'account_id': self.exp_account.id, 'debit': 800, 'credit': 0}),
                Command.create({'account_id': self.cash_account.id, 'debit': 0, 'credit': 800}),
            ],
        })
        move.action_post()
        line.invalidate_recordset()
        self.assertAlmostEqual(line.practical_percentage, 0.8, places=2)

        html, _tipo = self.env['ir.actions.report']._render_qweb_html(REPORT, [b.id])
        html = html.decode()

        self.assertIn('80.00%', html)

    def test_conta_da_posicao_mostra_o_proprio_realizado(self):
        """O que foi pedido: a linha da conta (sub) também mostra valor --
        antes só a linha-mãe (posição) somava algo."""
        b = self._budget()
        line = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': '2020-06-01',
            'line_ids': [
                Command.create({'account_id': self.exp_account.id, 'debit': 800, 'credit': 0}),
                Command.create({'account_id': self.cash_account.id, 'debit': 0, 'credit': 800}),
            ],
        })
        move.action_post()

        quebra = line._gl_actuals_by_account()
        self.assertAlmostEqual(quebra[self.exp_account.id]['practical'], -800.0, places=2,
                               msg="a quebra por conta tem de bater com o sinal P&L do practical_amount")

        html, _tipo = self.env['ir.actions.report']._render_qweb_html(REPORT, [b.id])
        html = html.decode()

        self.assertRegex(html, r'800[.,]00', "o valor da conta não apareceu formatado no PDF")

    def test_programado_conta_o_rascunho_realizado_nao(self):
        """A diferença entre as duas colunas da conta: Realizado é só o que
        está POSTADO; Programado soma também o rascunho do período."""
        b = self._budget()
        line = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})
        self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': '2020-06-01',
            'line_ids': [
                Command.create({'account_id': self.exp_account.id, 'debit': 800, 'credit': 0}),
                Command.create({'account_id': self.cash_account.id, 'debit': 0, 'credit': 800}),
            ],
        }).action_post()
        self.env['account.move'].create({  # fica em rascunho de propósito
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': '2020-06-02',
            'line_ids': [
                Command.create({'account_id': self.exp_account.id, 'debit': 300, 'credit': 0}),
                Command.create({'account_id': self.cash_account.id, 'debit': 0, 'credit': 300}),
            ],
        })

        quebra = line._gl_actuals_by_account()[self.exp_account.id]

        self.assertAlmostEqual(quebra['practical'], -800.0, places=2,
                               msg="rascunho não podia entrar no Realizado")
        self.assertAlmostEqual(quebra['programmed'], -1100.0, places=2,
                               msg="o Programado tem de somar o rascunho ao postado")

    def test_previsto_e_teorico_nao_descem_para_a_conta(self):
        """Regressão do que se tirou: houve uma versão que rateava o Previsto
        entre as contas -- num orçamento futuro, sem nada realizado, isso
        dividia o plano em partes iguais e dava cara de plano a um número que
        ninguém orçou (R$ -180.000 em 4 contas viravam -45.000 em cada)."""
        outra_conta = self.env['account.account'].create({
            'name': 'LabBudgetPrint Expense 2', 'code': 'LBPE2',
            'account_type': 'expense',
            'company_ids': [Command.link(self.company.id)],
        })
        self.position.account_ids = [Command.link(outra_conta.id)]
        b = self._budget()
        self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})

        html, _tipo = self.env['ir.actions.report']._render_qweb_html(REPORT, [b.id])
        html = html.decode()

        self.assertRegex(html, r'1[.,]000[.,]00', "o Previsto tem de seguir na linha da posição")
        self.assertNotRegex(html, r'500[.,]00',
                            "metade do Previsto apareceu na conta: o rateio voltou")

    def test_duas_contas_na_mesma_posicao_nao_se_misturam(self):
        """Edge case: a posição tem duas contas do razão -- cada uma mostra o
        seu próprio movimento, não a soma das duas."""
        outra_conta = self.env['account.account'].create({
            'name': 'LabBudgetPrint Expense 2', 'code': 'LBPE2',
            'account_type': 'expense',
            'company_ids': [Command.link(self.company.id)],
        })
        self.position.account_ids = [Command.link(outra_conta.id)]
        b = self._budget()
        line = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})
        self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': '2020-06-01',
            'line_ids': [
                Command.create({'account_id': self.exp_account.id, 'debit': 800, 'credit': 0}),
                Command.create({'account_id': self.cash_account.id, 'debit': 0, 'credit': 800}),
            ],
        }).action_post()
        self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': '2020-06-02',
            'line_ids': [
                Command.create({'account_id': outra_conta.id, 'debit': 300, 'credit': 0}),
                Command.create({'account_id': self.cash_account.id, 'debit': 0, 'credit': 300}),
            ],
        }).action_post()

        quebra = line._gl_actuals_by_account()

        self.assertAlmostEqual(quebra[self.exp_account.id]['practical'], -800.0, places=2)
        self.assertAlmostEqual(quebra[outra_conta.id]['practical'], -300.0, places=2)

    def test_quebra_por_conta_fecha_o_total_da_posicao(self):
        """A conferência que o olho faz no papel: as contas somadas têm de dar
        exatamente o valor da linha da posição, nos dois campos."""
        outra_conta = self.env['account.account'].create({
            'name': 'LabBudgetPrint Expense 2', 'code': 'LBPE2',
            'account_type': 'expense',
            'company_ids': [Command.link(self.company.id)],
        })
        self.position.account_ids = [Command.link(outra_conta.id)]
        b = self._budget()
        line = self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'position_id': self.position.id,
            'budget_amount': -1000})
        self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal.id, 'date': '2020-06-01',
            'line_ids': [
                Command.create({'account_id': self.exp_account.id, 'debit': 800, 'credit': 0}),
                Command.create({'account_id': outra_conta.id, 'debit': 300, 'credit': 0}),
                Command.create({'account_id': self.cash_account.id, 'debit': 0, 'credit': 1100}),
            ],
        }).action_post()
        line.invalidate_recordset()

        quebra = line._gl_actuals_by_account()

        self.assertAlmostEqual(sum(v['practical'] for v in quebra.values()),
                               line.practical_amount, places=2)
        self.assertAlmostEqual(sum(v['programmed'] for v in quebra.values()),
                               line.programmed_amount, places=2)

    def test_linha_so_com_conta_analitica_nao_entra_na_secao_2(self):
        """Erro em potencial: linha sem posição não pode gerar um grupo vazio
        ou quebrar a segunda seção."""
        b = self._budget()
        self.env['budget.line'].create({
            'budget_analytic_id': b.id, 'account_id': self.analytic.id,
            'budget_amount': -500})

        html, _tipo = self.env['ir.actions.report']._render_qweb_html(REPORT, [b.id])
        html = html.decode()

        self.assertIn('Nenhuma linha deste orçamento usa posição orçamentária.', html)
