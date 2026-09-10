# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestAgedReceivable(TransactionCase):
    """A view SQL não tem `create`, então não há constraint nem compute para
    exercitar: o que se prova aqui é a única regra que ela carrega -- em que
    faixa cada linha cai -- e que o total continua batendo com o razão.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Reaproveitar a empresa do banco em vez de criar uma: `res.company`
        # com o `account` instalado explode em NOT NULL de fiscalyear_last_day.
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Livraria de Teste'})
        cls.conta = cls.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)
        cls.diario = cls.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', cls.company.id)], limit=1)
        if not cls.conta or not cls.diario:
            cls.skipTest(cls, 'a empresa deste banco não tem conta a receber '
                              'ou diário de venda')
        cls.contrapartida = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_ids', 'in', cls.company.id),
        ], limit=1)

    def _lancar(self, vencimento, valor=100.0):
        """Um lançamento simples com uma perna na conta a receber."""
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.diario.id,
            'company_id': self.company.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {'account_id': self.conta.id,
                        'partner_id': self.partner.id,
                        'date_maturity': vencimento,
                        'debit': valor, 'credit': 0.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'partner_id': self.partner.id,
                        'debit': 0.0, 'credit': valor}),
            ],
        })
        move.action_post()
        return move

    def _linha(self, move):
        return self.env['liber.aged.receivable'].search([
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

    def test_dias_para_vencer_e_o_espelho_do_atraso(self):
        """Um dos dois é sempre zero: ou falta, ou passou. É o campo que o
        painel de Recebíveis usa para "vence nos próximos 30 dias"."""
        hoje = fields.Date.today()
        a_vencer = self._linha(self._lancar(hoje + timedelta(days=10)))
        self.assertEqual((a_vencer.days_to_due, a_vencer.days_overdue), (10, 0))
        vencida = self._linha(self._lancar(hoje - timedelta(days=5)))
        self.assertEqual((vencida.days_to_due, vencida.days_overdue), (0, 5))
        no_dia = self._linha(self._lancar(hoje))
        self.assertEqual((no_dia.days_to_due, no_dia.days_overdue), (0, 0))

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

        A comparação é com a fatia POSTADA do relatório. Desde 29/08 a view
        também carrega rascunho -- o financeiro provisiona assim --, e
        rascunho não está no razão por definição: ele não tem lançamento
        contábil. Somar os dois lados com réguas diferentes daria uma
        diferença que não é erro de ninguém.
        """
        self._lancar(fields.Date.today() - timedelta(days=5), 321.0)
        self.env.flush_all()
        self.env.cr.execute("""
            SELECT ROUND(SUM(l.amount_residual), 2)
              FROM account_move_line l
              JOIN account_move m ON m.id = l.move_id AND m.state = 'posted'
              JOIN account_account a ON a.id = l.account_id
             WHERE a.account_type = 'asset_receivable'
               AND ROUND(l.amount_residual, 2) <> 0
        """)
        razao = self.env.cr.fetchone()[0] or 0.0
        self.env.cr.execute(
            "SELECT ROUND(SUM(amount_total), 2) FROM liber_aged_receivable "
            "WHERE move_state = 'posted'")
        relatorio = self.env.cr.fetchone()[0] or 0.0
        self.assertAlmostEqual(float(relatorio), float(razao), 2)

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
                        'debit': 0.0, 'credit': 250.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'partner_id': self.partner.id,
                        'debit': 250.0, 'credit': 0.0}),
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
                        'debit': 70.0, 'credit': 0.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'partner_id': self.partner.id,
                        'debit': 0.0, 'credit': 70.0}),
            ],
        })
        move.action_post()
        linha = self._linha(move)
        self.assertFalse(linha.line_id.date_maturity or False)
        self.assertEqual(linha.amount_older, 70.0,
                         'sem vencimento, vale a data do lançamento')

    def test_rascunho_aparece_mas_marcado(self):
        """Rascunho ENTRA na view, e o filtro é que o esconde.

        Mudou em 29/08. Antes a view só lia `posted`, e o rascunho não existia
        para o relatório. Mas o financeiro da casa PROVISIONA EM RASCUNHO: no
        prod são 966 linhas no a pagar, R$ 4.080.175,51 que ninguém via.

        Rascunho não é dívida ainda — não tem número, não foi lançado — mas é
        compromisso conhecido, e quem planeja pagamento precisa vê-lo. Por
        isso ele entra na view com `move_state = 'draft'` e fica FORA por
        padrão, atrás do filtro `postados` que a ação já traz marcado.
        """
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.diario.id,
            'company_id': self.company.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {'account_id': self.conta.id,
                        'partner_id': self.partner.id,
                        'debit': 99.0, 'credit': 0.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'partner_id': self.partner.id,
                        'debit': 0.0, 'credit': 99.0}),
            ],
        })
        linha = self._linha(move)
        self.assertTrue(linha, 'o rascunho tem de existir na view')
        self.assertEqual(linha.move_state, 'draft')
        self.assertFalse(linha.can_reconcile,
                         'rascunho não concilia: não há lançamento contábil')
        # e o filtro padrão da tela o esconde
        so_postados = self.env['liber.aged.receivable'].search(
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
                        'debit': 40.0, 'credit': 0.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'debit': 0.0, 'credit': 40.0}),
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
            'move_type': 'out_invoice',
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
                        'debit': 0.0, 'credit': 60.0}),
                (0, 0, {'account_id': self.contrapartida.id,
                        'partner_id': self.partner.id,
                        'debit': 60.0, 'credit': 0.0}),
            ],
        })
        outro.action_post()
        self.assertTrue(self._linha(um_lado).can_reconcile,
                        'com os dois lados, passa a dar')

    # ------------------------------------------------ isolamento por empresa

    def test_regra_de_empresa_existe(self):
        """A view SQL não ganha o filtro de multi-empresa de graça.

        Modelo com tabela e `company_id` recebe do Odoo uma regra automática;
        `_auto = False` não recebe. Sem a regra explícita o relatório mostrava
        as seis empresas do grupo com uma só marcada no seletor, e cada
        editora enxergava a carteira das outras.
        """
        regra = self.env.ref(
            'liber_aged_receivable.liber_aged_receivable_company_rule')
        # O campo chama-se `global` mesmo -- palavra reservada do Python, e
        # por isso só se lê por índice.
        self.assertTrue(regra['global'],
                        'a regra tem de valer para todo mundo, inclusive o '
                        'administrador')
        self.assertEqual(regra.model_id.model, 'liber.aged.receivable')
        self.assertIn('company_ids', regra.domain_force,
                      'o filtro tem de ler o que está MARCADO no seletor '
                      '(`company_ids`), não o que a pessoa tem direito')

    def test_empresa_nao_ve_a_outra(self):
        """Com outra empresa marcada no seletor, a linha some da tela.

        O teste PRECISA de um usuário de verdade: `self.env` do
        `TransactionCase` roda como SUPERUSUÁRIO, e superusuário atravessa
        regra de registro sem olhar. Medir por ali daria verde com a regra
        apagada -- foi exatamente o que aconteceu na primeira versão deste
        teste.
        """
        gente = self.env.ref('base.user_admin')
        outra = self.env['res.company'].search(
            [('id', '!=', self.company.id)], limit=1)
        if not outra:
            self.skipTest('este banco tem uma empresa só')
        move = self._lancar(date.today() + timedelta(days=10))

        Relatorio = self.env['liber.aged.receivable'].with_user(gente)
        self.assertTrue(
            Relatorio.with_context(
                allowed_company_ids=[self.company.id]).search(
                    [('move_id', '=', move.id)]),
            'na própria empresa a linha tem de aparecer')

        de_fora = Relatorio.with_context(
            allowed_company_ids=[outra.id]).search([('move_id', '=', move.id)])
        self.assertFalse(de_fora,
                         'a linha de %s apareceu para quem está em %s'
                         % (self.company.name, outra.name))

        juntas = Relatorio.with_context(
            allowed_company_ids=[outra.id, self.company.id]).search(
                [('move_id', '=', move.id)])
        self.assertTrue(juntas, 'quem marca as duas empresas tem de ver as '
                                'duas -- a regra não pode fechar demais')

    # --------------------------------------------- o eixo do grupo econômico

    def test_sem_rede_o_grupo_e_o_proprio_cliente(self):
        """A regra da casa: quem não é rede é ele mesmo.

        Agrupar pelo many2one jogava 4.265 clientes num balde "Nenhum" -- o
        maior grupo da tela, e o que menos diz. O relatório lê o
        `commercial_group_display`, que já resolve isso na origem.
        """
        self.assertFalse(self.partner.partner_group_id,
                         'o parceiro do teste não deve pertencer a rede')
        move = self._lancar(date.today() + timedelta(days=10))
        self.assertEqual(self._linha(move).partner_group, self.partner.name,
                         'sem rede, o grupo tem de ser o nome do próprio '
                         'cliente -- e nunca vazio')

    def test_com_rede_o_grupo_e_a_rede(self):
        """E quem é de uma rede aparece sob o nome dela, não o da filial."""
        rede = self.env['liber.partner.group'].create({'name': 'Rede de Teste'})
        self.partner.partner_group_id = rede
        move = self._lancar(date.today() + timedelta(days=10))
        self.assertEqual(self._linha(move).partner_group, 'Rede de Teste',
                         'a filial tem de somar sob a rede')

    # ------------------------------------------- o botao de conciliar, em lote

    def test_botao_conciliar_abre_em_todas_as_linhas_elegiveis(self):
        """Varre TODAS as linhas com `can_reconcile` e exige que o botao abra.

        O teste unitario antigo provava um caso; este prova o conjunto. A casa
        relatou erro ao clicar no botao em 29/08, e uma varredura de 360 linhas
        no prod (n-1, EdLab Press e Hedra) nao reproduziu: o caminho ORM abre
        em 100% delas. Fica a varredura como guarda, para que uma regressao
        futura apareca como falha e nao como reclamacao de tela.
        """
        elegiveis = self.env['liber.aged.receivable'].search(
            [('can_reconcile', '=', True)], limit=200)
        if not elegiveis:
            self.skipTest('este banco nao tem par a conciliar')
        falhas = []
        for linha in elegiveis:
            try:
                acao = linha.action_open_reconcile()
            except Exception as e:                       # noqa: BLE001
                falhas.append('%s: %s' % (linha.move_name, e))
                continue
            if acao.get('res_model') != 'account.account.reconcile':
                falhas.append('%s abriu %s' % (linha.move_name,
                                               acao.get('res_model')))
            # KANBAN, nunca form: o form da OCA depende de um `env` que so o
            # kanban monta, e abrir como form estoura no Owl com
            # "this.env.exposeController is not a function". Foi o erro que a
            # casa relatou em 29/08, e o ORM nao o pega -- so esta guarda.
            elif acao.get('view_mode') != 'kanban':
                falhas.append('%s abriu em %s, nao kanban'
                              % (linha.move_name, acao.get('view_mode')))
            elif 'view_ref' not in acao.get('context', {}):
                falhas.append('%s sem view_ref: a tela viria sem o painel'
                              % linha.move_name)
        self.assertFalse(falhas, 'o botao falhou em %d de %d linhas:\n%s'
                         % (len(falhas), len(elegiveis), '\n'.join(falhas[:5])))

    def test_botao_conciliar_recusa_quando_nao_ha_par(self):
        """E o contrario: sem o outro lado, a recusa tem de ser explicada."""
        sem_par = self.env['liber.aged.receivable'].search(
            [('can_reconcile', '=', False), ('partner_id', '!=', False)],
            limit=1)
        if not sem_par:
            self.skipTest('este banco nao tem linha sem par')
        with self.assertRaises(UserError) as caixa:
            sem_par.action_open_reconcile()
        self.assertIn('Nothing to match here', str(caixa.exception),
                      'a recusa tem de dizer POR QUE nao ha o que casar')

    # ----------------------------------------------------- a acao de "Pagar"

    def test_pagar_abre_o_assistente_com_as_faturas(self):
        """Marcar linhas e pedir Pagar abre o assistente do Odoo."""
        fatura = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'livro', 'quantity': 1, 'price_unit': 250.0,
                'account_id': self.contrapartida.id})],
        })
        fatura.action_post()
        linha = self.env['liber.aged.receivable'].search(
            [('move_id', '=', fatura.id)])
        self.assertTrue(linha, 'a fatura postada tem de aparecer no relatório')

        acao = linha.action_registrar_pagamento()
        self.assertEqual(acao['res_model'], 'account.payment.register')
        self.assertEqual(acao['context']['active_model'], 'account.move')
        self.assertIn(fatura.id, acao['context']['active_ids'])

    def test_pagar_recusa_o_que_nao_e_fatura(self):
        """Pagamento solto não se paga: ele é o que paga.

        A recusa tem de EXPLICAR, e não estourar erro do framework quando o
        assistente do Odoo recebe um lançamento que não sabe liquidar.
        """
        move = self._lancar(date.today() + timedelta(days=5))
        linha = self._linha(move)
        self.assertTrue(linha)
        with self.assertRaises(UserError) as caixa:
            linha.action_registrar_pagamento()
        self.assertIn('None of the selected lines is an invoice',
                      str(caixa.exception))

    # ------------------------------------------------- rascunho nas ações

    def test_rascunho_recusa_conciliar_e_pagar(self):
        """As duas ações recusam rascunho, e explicam por quê.

        Sem isso o usuário clicaria e receberia erro do framework -- o
        assistente do Odoo não sabe liquidar documento que não foi lançado.
        """
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'name': 'livro', 'quantity': 1, 'price_unit': 80.0,
                'account_id': self.contrapartida.id})],
        })
        linha = self._linha(move)
        self.assertTrue(linha, 'a fatura em rascunho tem de aparecer')

        with self.assertRaises(UserError) as caixa:
            linha.action_registrar_pagamento()
        self.assertIn('draft', str(caixa.exception).lower())

        with self.assertRaises(UserError) as caixa:
            linha.action_open_reconcile()
        self.assertIn('draft', str(caixa.exception).lower())

    # ---------------------------------- a acao do menu, como a tela a chama

    def _fatura_postada(self, valor=250.0):
        fatura = self.env['account.move'].create({
            'move_type': 'out_invoice',
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
        acao = self.env.ref('liber_aged_receivable.liber_aged_receivable_pagar')
        return acao.with_user(usuario).with_context(
            active_model='liber.aged.receivable', active_ids=linhas.ids).run()

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
