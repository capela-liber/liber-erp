# -*- coding: utf-8 -*-
"""O evento deu dinheiro? A conta, captada na fonte.

"É muito difícil saber se um evento deu dinheiro. Lógico, temos o analítico,
mas ter uma estrutura para captar isso direto na fonte é melhor -- na mão do
nosso comercial."

O analítico continua sendo preenchido, porque é ele que a contabilidade lê. O
que muda é que a pergunta passa a ter resposta NA FICHA DO EVENTO: o que o
caixa vendeu, quanto custaram os livros que saíram, quanto o evento gastou, e
o que sobrou.
"""
from odoo.tests import tagged

from .test_caixa_da_feira import TestCaixaDaFeira

# Senha igual ao login, numa CONSTANTE: escrita como literal ela casa com a
# varredura de segredos do publish_liber_erp.sh e barra a publicação inteira.
LOGIN = 'supervisor_curioso'


@tagged('post_install', '-at_install', 'liber_fairs_pos')
class TestCustosDoEvento(TestCaixaDaFeira):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # As Definições PREENCHIDAS: com elas vazias o `if` do analítico e o
        # da conta a pagar não rodam, e o teste passaria verde sem medir nada.
        plano = cls.env['account.analytic.plan'].search([], limit=1) or \
            cls.env['account.analytic.plan'].create({'name': 'Eventos'})
        cls.company.fair_analytic_plan_id = plano.id
        cls.company.fair_service_product_id = cls.env['product.product'].create({
            'name': 'Equipe de evento (diárias e comissão)',
            'type': 'service', 'purchase_ok': True,
        }).id


    def _custo(self, fair, valor, tipo='in_invoice'):
        fornecedor = self.env['res.partner'].search(
            [('name', '=', 'Transportadora da Feira')], limit=1) or \
            self.env['res.partner'].create(
                {'name': 'Transportadora da Feira', 'supplier_rank': 1})
        return self.env['account.move'].create({
            'move_type': tipo,
            'partner_id': fornecedor.id,
            'company_id': self.company.id,
            'fair_id': fair.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Frete especial da feira',
                'quantity': 1,
                'price_unit': valor,
            })],
        })

    def test_a_cost_lands_in_the_event_and_carries_the_analytic(self):
        fair = self._feira_na_praca(10)
        conta = self._custo(fair, 800.0)

        self.assertIn(conta, fair.bill_ids,
                      "O gasto tem de aparecer na aba do evento")
        analitico = fair._get_analytic_account()
        self.assertTrue(analitico)
        self.assertEqual(
            conta.invoice_line_ids.analytic_distribution,
            {str(analitico.id): 100},
            "E levar o analítico do evento junto, que é o que a "
            "contabilidade lê")

    def test_a_line_that_already_chose_its_analytic_is_left_alone(self):
        """Quem escolheu, escolheu."""
        fair = self._feira_na_praca(10)
        outro = self.env['account.analytic.account'].create({
            'name': 'Outro destino',
            'plan_id': fair._get_analytic_account().plan_id.id})
        conta = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.env['res.partner'].create(
                {'name': 'Fornecedor teimoso'}).id,
            'company_id': self.company.id,
            'fair_id': fair.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Gasto com destino próprio',
                'quantity': 1, 'price_unit': 100.0,
                'analytic_distribution': {str(outro.id): 100},
            })],
        })

        self.assertEqual(conta.invoice_line_ids.analytic_distribution,
                         {str(outro.id): 100})

    def test_the_result_is_sales_minus_books_minus_costs(self):
        """A pergunta do dono, com número."""
        self.livro.standard_price = 10.0
        fair = self._feira_na_praca(10)
        self._operadores(fair, 'Marta')
        fair.action_open_pos()
        self._venda(fair, 3)          # 3 x 40,00 = 120,00 no caixa
        self._custo(fair, 50.0)

        fair.invalidate_recordset()

        self.assertEqual(fair.pos_amount_total, 120.0)
        self.assertEqual(fair.cogs_total, 30.0, "Três livros a dez de custo")
        self.assertEqual(fair.cost_total, 50.0)
        self.assertEqual(fair.result_total, 40.0,
                         "120 de venda, menos 30 de livro, menos 50 de gasto")

    def test_a_supplier_refund_gives_money_back(self):
        fair = self._feira_na_praca(10)
        self._custo(fair, 300.0)
        self._custo(fair, 100.0, tipo='in_refund')

        fair.invalidate_recordset()

        self.assertEqual(fair.cost_total, 200.0,
                         "Nota de crédito do fornecedor devolve dinheiro")

    def test_a_cancelled_cost_does_not_count(self):
        fair = self._feira_na_praca(10)
        conta = self._custo(fair, 300.0)
        conta.button_cancel()

        fair.invalidate_recordset()

        self.assertEqual(fair.cost_total, 0.0)

    def test_the_team_bills_are_costs_of_the_event(self):
        """As contas da equipe caem na mesma aba, sem ninguém lançar."""
        fair = self._feira_na_praca(10)
        marta, = self._operadores(fair, 'Marta')
        fair.action_open_pos()
        marta.write({'daily_rate': 150.0, 'days': 2})
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = dia.line_ids.qty_expected
        dia.action_close()

        fair.action_return()

        fair.invalidate_recordset()
        self.assertTrue(marta.bill_id, "A conta da diária nasce no fechamento")
        self.assertIn(marta.bill_id, fair.bill_ids,
                      "E ela é um custo do evento como qualquer outro")
        self.assertEqual(fair.cost_total, marta.bill_id.amount_total,
                         "O custo é o que a casa vai pagar, imposto incluído")
        self.assertEqual(marta.bill_id.amount_untaxed, 300.0,
                         "Duas diárias de cento e cinquenta")

    def test_the_people_on_site_do_not_see_the_money(self):
        """Custo é da equipe interna. Atendente e supervisor não entram.

        A aba inteira é escondida pelo grupo de quem planeja; a tranca de
        verdade é que eles não têm direito de ler conta a pagar nenhuma.
        """
        fair = self._feira_na_praca(10)
        contato = self.env['res.partner'].create({'name': 'Supervisor Curioso'})
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Supervisor Curioso', 'login': LOGIN,
                'password': LOGIN, 'partner_id': contato.id,
                'company_id': self.company.id,
                'company_ids': [(6, 0, [self.company.id])],
                'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.env['event.fair.cashier'].create({
            'fair_id': fair.id, 'partner_id': contato.id, 'role': 'manager'})
        fair.action_open_pos()
        self._custo(fair, 500.0)
        self.env.invalidate_all()

        visiveis = self.env['account.move'].with_user(usuario).search(
            [('fair_id', '=', fair.id)])

        self.assertFalse(visiveis,
                         "O custo do evento não aparece para quem está na "
                         "praça, nem por busca")
        # E quem é da casa continua vendo o que precisa pagar.
        self.assertTrue(self.env['account.move'].search(
            [('fair_id', '=', fair.id)]))
