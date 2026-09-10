# -*- coding: utf-8 -*-
"""Um caixa nascendo e fechando, na tela, com o perfil de quem opera a feira.

Escrito porque o dono tentou encerrar uma feira e levou um erro de
contabilidade -- "defina a conta de receita para esse produto" -- que os
testes de ORM não davam, porque no banco de teste as contas existem. O tour
não resolve o plano de contas da casa; o que ele garante é que o CAMINHO
existe e funciona ponta a ponta: digitar quantos caixas, abrir, e encerrar a
feira com uma sessão viva por baixo.

A sessão aberta é o caso difícil de propósito: com ela, abrir um segundo
caixa esbarra na trava do PDV (não se muda a configuração de um caixa que
está vendendo) e o encerramento tem de fechar dinheiro de verdade.
"""
from datetime import date

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs_pos_tour')
class TestTourCaixa(HttpCase):

    def test_um_caixa_nasce_e_fecha_na_tela(self):
        company = self.env.company
        armazem = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        livro = self.env['product.product'].create({
            'name': 'Livro do Caixa', 'type': 'consu', 'is_storable': True,
            'list_price': 50.0, 'standard_price': 20.0})
        self.env['stock.quant']._update_available_quantity(
            livro, armazem.lot_stock_id, 40)

        fair = self.env['event.fair'].create({
            'name': 'Feira do Caixa',
            'date_start': date.today(), 'date_end': date.today(),
            'company_id': company.id,
            'line_ids': [(0, 0, {
                'product_id': livro.id, 'qty_planned': 10})]})
        fair.action_plan()
        saida = fair.action_ship()
        saida.action_assign()
        for move in saida.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        saida.button_validate()
        fair.picking_ids.filtered(
            lambda p: p.fair_operation == 'receipt'
            and p.state != 'done').action_fair_check()

        # O primeiro caixa já existe e JÁ VENDEU: é o que torna o encerramento
        # um fechamento de verdade, com lançamento e tudo. O tour soma o
        # segundo operador na tela.
        marta = self.env['res.partner'].create({'name': 'Marta do Caixa'})
        self.env['res.partner'].create({'name': 'Joana do Caixa'})
        self.env['event.fair.cashier'].create(
            {'fair_id': fair.id, 'partner_id': marta.id})
        fair.action_open_pos()
        sessao = self.env['pos.session'].create({
            'config_id': fair.pos_config_id.id, 'user_id': self.env.user.id})
        sessao.action_pos_session_open()
        pedido = self.env['pos.order'].create({
            'company_id': company.id, 'session_id': sessao.id,
            'amount_tax': 0.0, 'amount_total': 50.0, 'amount_paid': 50.0,
            'amount_return': 0.0, 'state': 'paid',
            'lines': [(0, 0, {
                'product_id': livro.id, 'qty': 1, 'price_unit': 50.0,
                'price_subtotal': 50.0, 'price_subtotal_incl': 50.0})]})
        metodo = sessao.payment_method_ids.filtered(
            lambda m: m.type == 'cash')[:1] or sessao.payment_method_ids[:1]
        self.env['pos.payment'].create({
            'pos_order_id': pedido.id, 'payment_method_id': metodo.id,
            'amount': 50.0, 'session_id': sessao.id})
        pedido._create_order_picking()

        # o dia se fecha antes: o retorno conta a mesa, e a mesa se conta com
        # o dia fechado (foi assim que ele achou o "Não disponível")
        dia = fair.day_ids[0]
        dia.action_fill()
        dia.line_ids.qty_counted = dia.line_ids.qty_expected
        dia.action_close()

        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Feira do Caixa', 'login': 'tour_caixa',
                'password': 'tour_caixa', 'lang': 'pt_BR',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': [
                    (4, self.env.ref('liber_fairs.group_fair_manager').id),
                    # opera o PDV: é quem vende no balcão da feira
                    (4, self.env.ref('point_of_sale.group_pos_user').id),
                ]})
        self.assertTrue(usuario)

        self.start_tour('/odoo', 'fair_pos_birth_tour', login='tour_caixa')

        fair.invalidate_recordset()
        todos = fair.with_context(active_test=False)
        self.assertEqual(
            len(todos.pos_config_ids), 2,
            "O segundo caixa tinha de nascer na tela. Operadores: %s | "
            "caixas: %s" % (fair.cashier_ids.mapped('name'),
                            todos.pos_config_ids.mapped('name')))
        self.assertIn('Joana', ' '.join(todos.pos_config_ids.mapped('name')),
                      "E com o nome do operador escolhido no tour")

        self.start_tour('/odoo', 'fair_pos_death_tour', login='tour_caixa')

        # active_test=False: caixa arquivado some do One2many, e depois do
        # retorno os dois estão arquivados -- que é exatamente o que se quer
        # provar.
        todos.invalidate_recordset()
        sessao.invalidate_recordset()
        self.assertEqual(sessao.state, 'closed',
                         "E o caixa que vendia tinha de fechar no retorno")
        self.assertFalse(todos.pos_config_ids.filtered('active'),
                         "Os caixas saem da lista quando a feira volta")
        self.assertEqual(fair.state, 'returned')
