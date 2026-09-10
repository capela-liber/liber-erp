# -*- coding: utf-8 -*-
"""O dinheiro de quem trabalhou o evento.

Três regras, e as três foram escolhidas para caber numa frase dita em voz
alta para quem está no balcão:

  - a COMISSÃO é percentual sobre o que a PESSOA vendeu no caixa dela. Quem
    vendeu mais, ganha mais;
  - a DIÁRIA é o valor combinado, vezes os dias que a pessoa trabalhou;
  - a PERDA do evento, a custo, rateia IGUAL entre a equipe. A mesa é guarda
    coletiva e ninguém sabe de quem era o exemplar que sumiu.

E uma que é de decência: conta a pagar nunca é negativa. O que a comissão e a
diária não cobrirem fica escrito como "ainda devido", para a conversa
acontecer com número em cima da mesa -- e não vira cobrança automática.
"""
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_caixa_da_feira import TestCaixaDaFeira


@tagged('post_install', '-at_install', 'liber_fairs_pos')
class TestComissoes(TestCaixaDaFeira):

    def _equipe(self, fair, *nomes):
        linhas = self._operadores(fair, *nomes)
        fair.action_open_pos()
        return linhas

    def _perder(self, fair, qty, custo=None):
        """Uma perda a custo, para o rateio ter o que dividir."""
        if custo is not None:
            self.livro.standard_price = custo
        return self.env['event.fair.loss'].create({
            'fair_id': fair.id, 'product_id': self.livro.id, 'qty': qty,
            'reason': 'missing', 'stage': 'fair'})

    # --- a conta ---------------------------------------------------------
    def test_commission_is_on_what_this_person_sold(self):
        fair = self._feira_na_praca(20)
        marta, joana = self._equipe(fair, 'Marta', 'Joana')
        marta.commission_pc = 10.0
        joana.commission_pc = 10.0
        self._venda(fair, 3)          # vende no caixa da PRIMEIRA

        marta.invalidate_recordset()
        joana.invalidate_recordset()
        self.assertEqual(marta.pos_amount, 120.0, "Três a quarenta")
        self.assertEqual(marta.commission_amount, 12.0)
        self.assertEqual(joana.pos_amount, 0.0,
                         "Ela não vendeu no caixa dela")
        self.assertEqual(joana.commission_amount, 0.0)

    def test_dailies_are_rate_times_days(self):
        fair = self._feira_na_praca(10)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 150.0, 'days': 3})
        self.assertEqual(marta.daily_amount, 450.0)

    def test_the_loss_is_split_equally(self):
        """A mesa é de todos: a perda divide igual, e não por quem vendeu."""
        fair = self._feira_na_praca(20)
        marta, joana = self._equipe(fair, 'Marta', 'Joana')
        marta.commission_pc = 10.0
        self._venda(fair, 3)          # só a Marta vendeu
        self._perder(fair, 4, custo=25.0)   # 100 de perda

        marta.invalidate_recordset()
        joana.invalidate_recordset()
        self.assertEqual(marta.loss_share, 50.0)
        self.assertEqual(joana.loss_share, 50.0,
                         "Quem não vendeu também responde pela mesa")

    def test_what_is_left_after_the_loss_is_what_gets_paid(self):
        fair = self._feira_na_praca(20)
        marta, joana = self._equipe(fair, 'Marta', 'Joana')
        marta.write({'commission_pc': 10.0, 'daily_rate': 100.0, 'days': 2})
        joana.write({'daily_rate': 100.0, 'days': 2})
        self._venda(fair, 3)                 # 120 vendidos -> 12 de comissão
        self._perder(fair, 4, custo=25.0)    # 100 de perda -> 50 para cada

        marta.invalidate_recordset()
        joana.invalidate_recordset()
        self.assertEqual(marta.net_amount, 12.0 + 200.0 - 50.0)
        self.assertEqual(joana.net_amount, 200.0 - 50.0)
        self.assertFalse(marta.uncovered_loss)

    def test_a_bill_is_never_negative(self):
        """Ninguém paga para ter trabalhado; o que falta fica escrito."""
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 20.0, 'days': 1})
        self._perder(fair, 4, custo=25.0)    # 100 de perda para uma pessoa

        marta.invalidate_recordset()
        self.assertEqual(marta.net_amount, 0.0)
        self.assertEqual(marta.uncovered_loss, 80.0,
                         "Cem de perda menos vinte de diária")

    # --- a conta a pagar --------------------------------------------------
    def _fechar(self, fair):
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = dia.line_ids.qty_expected
        dia.action_close()
        despacho = fair.action_return()
        despacho.action_assign()
        for move in despacho.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        despacho.button_validate()
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'return' and p.state != 'done')
        if chegada:
            chegada.action_assign()
            for move in chegada.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            chegada.button_validate()
        return fair

    def _preparar_contabilidade(self):
        plano = self.env['account.analytic.plan'].search([], limit=1) or \
            self.env['account.analytic.plan'].create({'name': 'Eventos'})
        servico = self.env['product.product'].create({
            'name': 'Equipe de evento', 'type': 'service'})
        self.company.write({
            'fair_analytic_plan_id': plano.id,
            'fair_service_product_id': servico.id,
        })
        return servico

    def test_the_bill_carries_the_event_and_the_analytic(self):
        servico = self._preparar_contabilidade()
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 100.0, 'days': 2})
        self._fechar(fair)

        fair.action_generate_bills()

        marta.invalidate_recordset()
        conta = marta.bill_id
        self.assertTrue(conta, "Cada pessoa tem a sua conta a pagar")
        self.assertEqual(conta.move_type, 'in_invoice')
        self.assertEqual(conta.partner_id, marta.partner_id)
        # O VALOR SEM IMPOSTO é o que a pessoa tem a receber. Se a conta leva
        # imposto ou não é decisão do produto de serviço que a casa
        # configurou -- o módulo não arbitra tributo de ninguém.
        self.assertEqual(conta.amount_untaxed, 200.0)
        self.assertIn(fair.code, conta.ref, "O evento no nome da conta")
        linha = conta.invoice_line_ids
        self.assertEqual(linha.product_id, servico)
        self.assertEqual(
            linha.analytic_distribution,
            {str(fair.analytic_account_id.id): 100},
            "E o evento no analítico, que é onde o custo dele se junta")

    def test_bills_are_not_created_twice(self):
        self._preparar_contabilidade()
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 100.0, 'days': 1})
        self._fechar(fair)
        fair.action_generate_bills()
        primeira = marta.bill_id
        fair.action_generate_bills()
        marta.invalidate_recordset()
        self.assertEqual(marta.bill_id, primeira)

    def test_no_bill_before_the_event_comes_home(self):
        """O rateio depende do que o retorno apurou."""
        self._preparar_contabilidade()
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 100.0, 'days': 1})
        with self.assertRaises(UserError):
            fair.action_generate_bills()

    def test_no_service_product_no_bill(self):
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 100.0, 'days': 1})
        self._fechar(fair)
        self.company.fair_service_product_id = False
        with self.assertRaises(UserError):
            fair.action_generate_bills()

    def test_who_owes_more_than_earned_gets_no_bill(self):
        self._preparar_contabilidade()
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 10.0, 'days': 1})
        self._perder(fair, 4, custo=25.0)
        self._fechar(fair)

        fair.action_generate_bills()

        marta.invalidate_recordset()
        self.assertFalse(marta.bill_id,
                         "Não se emite conta de valor zero")
        self.assertEqual(marta.uncovered_loss, 90.0)

    def test_days_start_as_the_length_of_the_event(self):
        """Corrigir para menos é mais fácil do que lembrar de preencher."""
        fair = self.env['event.fair'].create({
            'name': 'Feira de três dias',
            'date_start': date(2026, 9, 20),
            'date_end': date(2026, 9, 22),
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': 5})]})
        linha = self.env['event.fair.cashier'].create({
            'fair_id': fair.id,
            'partner_id': self.env['res.partner'].create(
                {'name': 'Quem trabalha os três'}).id})
        self.assertEqual(linha.days, 3)

    # --- quem paga por qual perda ----------------------------------------
    def test_what_never_arrived_is_not_the_teams_bill(self):
        """"Se não saiu do depósito porque não tinha, não é perda deles."

        E o exemplar que saiu do depósito e não chegou na mesa também não é:
        ele sumiu na estrada, e quem estava no balcão não tinha como cuidar
        dele. A equipe responde pelo que sumiu SOB A GUARDA dela.
        """
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 100.0, 'days': 1})

        # perda nascida de uma CHEGADA: não chegou na mesa
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt')
        da_estrada = self.env['event.fair.loss'].create({
            'fair_id': fair.id, 'product_id': self.livro.id, 'qty': 4,
            'reason': 'not_received', 'stage': 'fair',
            'picking_id': chegada[:1].id})

        self.assertFalse(da_estrada.charged_to_team,
                         "Não chegou: não é da conta de quem estava lá")
        marta.invalidate_recordset()
        self.assertEqual(marta.loss_share, 0.0)
        self.assertEqual(marta.net_amount, 100.0,
                         "A diária dele fica inteira")

    def test_what_vanished_from_the_table_is(self):
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 100.0, 'days': 1})
        da_mesa = self._perder(fair, 2, custo=25.0)   # lançada à mão: na mesa

        self.assertTrue(da_mesa.charged_to_team)
        marta.invalidate_recordset()
        self.assertEqual(marta.loss_share, 50.0)
        self.assertEqual(marta.net_amount, 50.0)

    def test_the_manager_can_decide_otherwise(self):
        """O gerente sabe de coisa que o sistema não sabe."""
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 100.0, 'days': 1})
        perda = self._perder(fair, 2, custo=25.0)

        perda.charged_to_team = False

        marta.invalidate_recordset()
        self.assertEqual(marta.loss_share, 0.0)
        self.assertEqual(marta.net_amount, 100.0)

    def test_the_fair_shows_both_numbers(self):
        """Perda total e a parte que a equipe divide são coisas diferentes."""
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        chegada = fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt')
        self.env['event.fair.loss'].create({
            'fair_id': fair.id, 'product_id': self.livro.id, 'qty': 4,
            'reason': 'not_received', 'stage': 'fair',
            'picking_id': chegada[:1].id})
        self._perder(fair, 2, custo=25.0)

        fair.invalidate_recordset()
        # O custo é CONGELADO no lançamento: os quatro primeiros a 20 (o
        # custo do título no setUp) e os dois seguintes a 25.
        self.assertEqual(fair.loss_total, 130.0)
        self.assertEqual(fair.team_loss_total, 50.0,
                         "Só os dois que sumiram da mesa")

    # --- o fechamento já deixa pronto -------------------------------------
    def test_closing_the_event_leaves_the_bills_ready(self):
        """"No fechamento, estamos criando as bills?" -- agora sim.

        Em rascunho: criar conta a pagar não é pagar, e quem confere e lança
        é o financeiro. O que isso evita é o esquecimento -- a equipe foi
        embora, o evento fechou, e três semanas depois alguém pergunta da
        diária.
        """
        self._preparar_contabilidade()
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 120.0, 'days': 2})

        self._fechar(fair)

        marta.invalidate_recordset()
        self.assertTrue(marta.bill_id,
                        "Encerrar o evento tinha de deixar a conta pronta")
        self.assertEqual(marta.bill_id.state, 'draft',
                         "Em rascunho: criar não é pagar")
        self.assertEqual(marta.bill_id.amount_untaxed, 240.0)

    def test_closing_without_numbers_creates_nothing(self):
        """Quem não tem número não ganha conta -- e o evento volta igual."""
        self._preparar_contabilidade()
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')

        self._fechar(fair)

        marta.invalidate_recordset()
        self.assertFalse(marta.bill_id)
        self.assertEqual(fair.state, 'returned')

    def test_a_broken_accounting_does_not_hold_the_stock(self):
        """Sem produto de serviço, o evento volta assim mesmo."""
        fair = self._feira_na_praca(20)
        marta, = self._equipe(fair, 'Marta')
        marta.write({'daily_rate': 100.0, 'days': 1})
        self.company.fair_service_product_id = False

        self._fechar(fair)

        self.assertEqual(fair.state, 'returned',
                         "Estoque não espera contabilidade")
        self.assertFalse(marta.bill_id)

    # --- o que se combina, e quando ---------------------------------------
    def _feira_em_rascunho(self):
        return self.env['event.fair'].create({
            'name': 'Feira que ainda é ideia',
            'date_start': date(2026, 9, 20), 'date_end': date(2026, 9, 22),
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'product_id': self.livro.id, 'qty_planned': 10})]})

    def test_no_commission_before_the_event_is_planned(self):
        """Combinar comissão no rascunho é combinar no vazio.

        É o Planejar que monta os dias e abre o analítico; antes disso o
        evento ainda pode não acontecer.
        """
        fair = self._feira_em_rascunho()
        marta, = self._operadores(fair, 'Marta')
        self.assertEqual(fair.state, 'draft')

        with self.assertRaises(UserError):
            marta.commission_pc = 10.0
        with self.assertRaises(UserError):
            marta.write({'daily_rate': 100.0, 'days': 2})

    def test_after_planning_the_money_can_be_agreed(self):
        fair = self._feira_em_rascunho()
        marta, = self._operadores(fair, 'Marta')
        fair.action_plan()

        marta.write({'commission_pc': 10.0, 'daily_rate': 100.0, 'days': 2})

        self.assertEqual(marta.commission_pc, 10.0)
        self.assertEqual(marta.daily_amount, 200.0,
                         "Duas diárias de cem")

    def test_the_draft_still_takes_the_team(self):
        """A trava é do DINHEIRO, e não de quem trabalha o evento.

        Quem monta a feira escala a equipe junto com a grade; o que espera o
        planejamento é o que se combina de pagamento.
        """
        fair = self._feira_em_rascunho()
        marta, = self._operadores(fair, 'Marta')

        marta.role = 'manager'

        self.assertEqual(marta.role, 'manager')
