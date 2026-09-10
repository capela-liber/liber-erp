# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestAgedPayable(TransactionCase):
    """Espelho do teste do a receber, com uma pergunta a mais: o SINAL.

    A dívida com fornecedor nasce a crédito no razão (residual negativo) e a
    tela tem de mostrá-la positiva. Se a inversão do SELECT quebrar, o
    relatório inteiro vira negativo e ninguém nota olhando -- por isso há
    teste próprio para ela.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Reaproveitar a empresa do banco em vez de criar uma: `res.company`
        # com o `account` instalado explode em NOT NULL de fiscalyear_last_day.
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Gráfica de Teste'})
        cls.conta = cls.env['account.account'].search([
            ('account_type', '=', 'liability_payable'),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)
        cls.diario = cls.env['account.journal'].search([
            ('type', '=', 'purchase'), ('company_id', '=', cls.company.id)], limit=1)
        if not cls.conta or not cls.diario:
            cls.skipTest(cls, 'a empresa deste banco não tem conta a pagar '
                              'ou diário de compra')
        cls.contrapartida = cls.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)

    def _lancar(self, vencimento, valor=100.0):
        """Um lançamento simples com uma perna na conta a pagar."""
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.diario.id,
            'company_id': self.company.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {'account_id': self.conta.id,
                        'partner_id': self.partner.id,
                        'date_maturity': vencimento,
                        'debit': 0.0, 'credit': valor}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'partner_id': self.partner.id,
                        'debit': valor, 'credit': 0.0}),
            ],
        })
        move.action_post()
        return move

    def _linha(self, move):
        return self.env['liber.aged.payable'].search([
            ('move_id', '=', move.id)])

    # ------------------------------------------------------- caminho feliz
    def test_faixas(self):
        """Cada vencimento cai na sua faixa, e só na sua."""
        hoje = fields.Date.today()
        casos = [
            (hoje + timedelta(days=10), 'amount_current'),
            (hoje - timedelta(days=15), 'amount_30'),
            (hoje - timedelta(days=45), 'amount_60'),
            (hoje - timedelta(days=75), 'amount_90'),
            (hoje - timedelta(days=100), 'amount_120'),
            (hoje - timedelta(days=400), 'amount_older'),
        ]
        todos = ['amount_current', 'amount_30', 'amount_60',
                 'amount_90', 'amount_120', 'amount_older']
        for vencimento, esperado in casos:
            move = self._lancar(vencimento)
            linha = self._linha(move)
            self.assertEqual(len(linha), 1,
                             'o lançamento devia render UMA linha no relatório')
            self.assertEqual(linha[esperado], 100.0,
                             'vencimento %s devia cair em %s' % (vencimento, esperado))
            for campo in todos:
                if campo != esperado:
                    self.assertEqual(linha[campo], 0.0,
                                     '%s devia estar zerado' % campo)
            self.assertEqual(linha.amount_total, 100.0)

    def test_bordas_das_faixas(self):
        """Os limites 30/31 e 120/121 caem do lado que a tela do Odoo diz."""
        hoje = fields.Date.today()
        for dias, campo in ((0, 'amount_current'), (1, 'amount_30'),
                            (30, 'amount_30'), (31, 'amount_60'),
                            (120, 'amount_120'), (121, 'amount_older')):
            move = self._lancar(hoje - timedelta(days=dias))
            self.assertEqual(self._linha(move)[campo], 100.0,
                             '%d dia(s) de atraso devia cair em %s' % (dias, campo))

    def test_total_bate_com_o_razao(self):
        """A soma do relatório é a soma do residual das contas a receber.

        É o teste que importa: relatório que não fecha com o razão é pior do
        que relatório nenhum, porque parece confiável.
        """
        self._lancar(fields.Date.today() - timedelta(days=5), 321.0)
        self.env.flush_all()
        self.env.cr.execute("""
            SELECT ROUND(SUM(l.amount_residual), 2)
              FROM account_move_line l
              JOIN account_move m ON m.id = l.move_id AND m.state = 'posted'
              JOIN account_account a ON a.id = l.account_id
             WHERE a.account_type = 'liability_payable'
               AND ROUND(l.amount_residual, 2) <> 0
        """)
        razao = self.env.cr.fetchone()[0] or 0.0
        self.env.cr.execute(
            'SELECT ROUND(SUM(amount_total), 2) FROM liber_aged_payable')
        relatorio = self.env.cr.fetchone()[0] or 0.0
        # o sinal: o relatório mostra a dívida positiva, o razão a guarda
        # negativa. É a inversão do SELECT, e é ela que se prova aqui.
        self.assertAlmostEqual(float(relatorio), -float(razao), 2)

    # ------------------------------------------------------------ arestas
    def test_linha_conciliada_some(self):
        """Baixada a linha, ela sai do relatório -- é o que faz a tela servir
        de lista de cobrança e não de arquivo morto."""
        devido = self._lancar(fields.Date.today() - timedelta(days=10), 250.0)
        pago = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.diario.id,
            'company_id': self.company.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {'account_id': self.conta.id,
                        'partner_id': self.partner.id,
                        'debit': 250.0, 'credit': 0.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'partner_id': self.partner.id,
                        'debit': 0.0, 'credit': 250.0}),
            ],
        })
        pago.action_post()
        self.assertTrue(self._linha(devido), 'antes da baixa devia aparecer')
        pernas = (devido.line_ids + pago.line_ids).filtered(
            lambda l: l.account_id == self.conta)
        pernas.reconcile()
        self.env.flush_all()
        self.assertFalse(self._linha(devido), 'depois da baixa devia sumir')

    def test_sem_vencimento_usa_a_data_do_lancamento(self):
        """Pagamento avulso não tem vencimento. Sem o COALESCE ele iria parar
        em 'Não vencido' e o atraso ficaria invisível."""
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.diario.id,
            'company_id': self.company.id,
            'date': fields.Date.today() - timedelta(days=200),
            'line_ids': [
                (0, 0, {'account_id': self.conta.id,
                        'partner_id': self.partner.id,
                        'debit': 0.0, 'credit': 70.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'partner_id': self.partner.id,
                        'debit': 70.0, 'credit': 0.0}),
            ],
        })
        move.action_post()
        linha = self._linha(move)
        self.assertFalse(linha.line_id.date_maturity or False)
        self.assertEqual(linha.amount_older, 70.0,
                         'sem vencimento, vale a data do lançamento')

    def test_rascunho_aparece_mas_marcado(self):
        """Rascunho ENTRA na view, e o filtro é que o esconde.

        É aqui que a mudança de 29/08 mais importa: o financeiro da casa
        PROVISIONA EM RASCUNHO. No prod são 966 linhas no a pagar somando
        R$ 4.080.175,51 -- Hedra R$ 1,20 mi, EdLab Press R$ 1,03 mi, Saíra
        R$ 1,01 mi, Logopoiese R$ 764 mil -- que o relatório não mostrava.

        Rascunho não é dívida ainda, mas é compromisso conhecido: quem planeja
        pagamento precisa vê-lo. Entra na view com `move_state = 'draft'` e
        fica fora por padrão, atrás do filtro que a ação já traz marcado.
        """
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.diario.id,
            'company_id': self.company.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {'account_id': self.conta.id,
                        'partner_id': self.partner.id,
                        'debit': 0.0, 'credit': 99.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'partner_id': self.partner.id,
                        'debit': 99.0, 'credit': 0.0}),
            ],
        })
        linha = self._linha(move)
        self.assertTrue(linha, 'o rascunho tem de existir na view')
        self.assertEqual(linha.move_state, 'draft')
        self.assertFalse(linha.can_reconcile,
                         'rascunho não concilia: não há lançamento contábil')
        so_postados = self.env['liber.aged.payable'].search(
            [('move_id', '=', move.id), ('move_state', '=', 'posted')])
        self.assertFalse(so_postados,
                         'com o filtro padrão, o rascunho não aparece')

    # -------------------------------------------------------------- erros
    def test_conciliar_sem_cliente_recusa(self):
        """Linha sem parceiro não tem para onde pular -- e o erro tem de
        dizer o que fazer, não só que não deu."""
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.diario.id,
            'company_id': self.company.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {'account_id': self.conta.id,
                        'debit': 0.0, 'credit': 40.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'debit': 40.0, 'credit': 0.0}),
            ],
        })
        move.action_post()
        linha = self._linha(move)
        self.assertTrue(linha, 'linha sem cliente NÃO deve ser escondida')
        with self.assertRaises(UserError):
            linha.action_open_reconcile()

    def test_abrir_documento(self):
        """O botão devolve o próprio lançamento."""
        move = self._lancar(fields.Date.today() - timedelta(days=3))
        acao = self._linha(move).action_open_move()
        self.assertEqual(acao['res_model'], 'account.move')
        self.assertEqual(acao['res_id'], move.id)

    def test_parceiro_no_razao_errado(self):
        """Quem nunca emitiu documento deste lado é marcado.

        Foi a ADOBE SYSTEMS que fez este campo existir: 34 pagamentos numa
        conta de cliente e nenhuma fatura de cliente na vida -- é fornecedor.
        Nenhuma fatura está a caminho, então cobrar ou conciliar não resolve;
        o conserto é reclassificar. A tela precisa dizer isso sozinha.
        """
        move = self._lancar(fields.Date.today() - timedelta(days=5))
        linha = self._linha(move)
        self.assertTrue(linha.partner_off_ledger,
                        'parceiro sem documento deste lado devia ser marcado')

        # Emitido o documento, o parceiro passa a pertencer a este razão.
        doc = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.diario.id,
            'company_id': self.company.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'linha',
                'quantity': 1.0,
                'price_unit': 10.0,
                'account_id': self.contrapartida.id,
            })],
        })
        doc.action_post()
        self.assertFalse(self._linha(move).partner_off_ledger,
                         'com documento emitido, o parceiro deixa de ser '
                         'marcado como razão errado')

    def test_can_reconcile_exige_os_dois_lados(self):
        """Só há o que conciliar quando existem débito E crédito na conta.

        O caso real: 28 linhas de -335,00 do mesmo parceiro, zero do outro
        lado. O botão aparecia e recusava depois do clique.
        """
        um_lado = self._lancar(fields.Date.today() - timedelta(days=10))
        self.assertFalse(self._linha(um_lado).can_reconcile,
                         'um lado só não dá para conciliar')
        with self.assertRaises(UserError):
            self._linha(um_lado).action_open_reconcile()

        outro = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.diario.id,
            'company_id': self.company.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {'account_id': self.conta.id,
                        'partner_id': self.partner.id,
                        'debit': 60.0, 'credit': 0.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'partner_id': self.partner.id,
                        'debit': 0.0, 'credit': 60.0}),
            ],
        })
        outro.action_post()
        self.assertTrue(self._linha(um_lado).can_reconcile,
                        'com os dois lados, passa a dar')

    # ---------------------------------- a acao do menu, como a tela a chama

    def _fatura_postada(self, valor=250.0):
        fatura = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'livro', 'quantity': 1, 'price_unit': valor,
                'account_id': self.contrapartida.id})],
        })
        fatura.action_post()
        return fatura

    def _usuario(self, login, grupos):
        return self.env['res.users'].create({
            'name': login, 'login': login,
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])],
            'group_ids': [(6, 0, [self.env.ref(g).id for g in grupos])],
        })

    def _rodar_acao(self, usuario, linhas):
        acao = self.env.ref('liber_aged_payable.liber_aged_payable_pagar')
        return acao.with_user(usuario).with_context(
            active_model='liber.aged.payable', active_ids=linhas.ids).run()

    def test_acao_pagar_roda_para_o_financeiro(self):
        """O menu Acoes passa pela ACAO DE SERVIDOR, nao pelo metodo.

        No 19 uma acao de servidor sem grupo exige direito de ESCRITA no
        modelo (`_can_execute_action_on_records`), e a view SQL nao tem
        escrita para ninguem: o metodo passava no teste e a tela dava "Erro
        de acesso" para todo mundo, o admin inclusive. Por isso aqui se roda
        a acao, com o perfil de quem usa a tela e com o admin.
        """
        fatura = self._fatura_postada()
        linha = self._linha(fatura)
        self.assertTrue(linha)
        financeiro = self._usuario('financeiro_acao', [
            'base.group_user', 'account.group_account_user'])
        for usuario in (financeiro, self.env.ref('base.user_admin')):
            resultado = self._rodar_acao(usuario, linha)
            self.assertEqual(resultado['res_model'], 'account.payment.register',
                             usuario.login)
            self.assertIn(fatura.id, resultado['context']['active_ids'])

    def test_acao_pagar_recusa_quem_nao_e_do_financeiro(self):
        """Quem nao tem o perfil do Financeiro nao baixa por aqui."""
        fatura = self._fatura_postada()
        linha = self._linha(fatura)
        estranho = self._usuario('estranho_acao', ['base.group_user'])
        with self.assertRaises(AccessError):
            self._rodar_acao(estranho, linha)

    def test_acao_pagar_explica_o_que_nao_e_fatura(self):
        """Pela acao, a recusa continua sendo a explicada, nao a do framework."""
        move = self._lancar(date.today() + timedelta(days=5))
        linha = self._linha(move)
        financeiro = self._usuario('financeiro_acao2', [
            'base.group_user', 'account.group_account_user'])
        with self.assertRaises(UserError) as caixa:
            self._rodar_acao(financeiro, linha)
        self.assertIn('None of the selected lines is an invoice',
                      str(caixa.exception))
