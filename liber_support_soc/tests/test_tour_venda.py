# -*- coding: utf-8 -*-
"""Clicar em tudo: o assistente pela tela de verdade.

Pedido da direção depois de sentir "alguma instabilidade" na tela. A suíte de
servidor prova o efeito no banco e não prova que o formulário aguenta o uso --
foi assim que um `<div>` dentro de `<group>` derrubou a tela no cliente com a
view válida no servidor. Nenhum teste de Python teria pegado; este pega.
"""
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestVendaTour(HttpCase):

    def test_assistente_pela_tela(self):
        partner = self.env['res.partner'].create({
            'name': 'Livraria do Tour', 'is_company': True,
            'allow_consignment': True,
        })
        self.env['product.product'].create({
            'name': 'Livro do Tour', 'type': 'consu', 'is_storable': True,
            'list_price': 80.0, 'sale_ok': True,
        })
        team = self.env['liber.support.team'].create({
            'name': 'Comercial do Tour', 'company_id': self.env.company.id,
            'alias_name': 'tour-venda-test',
        })
        ticket = self.env['liber.support.ticket'].create({
            'name': 'Pedido do Tour', 'team_id': team.id,
            'partner_id': partner.id,
        })

        # O assistente nasce com o texto das mensagens de e-mail do chamado,
        # e o botão "Reler" reprocessa justamente isso. Sem conversa semeada o
        # tour clicaria num botão que não tem o que fazer.
        ticket.message_post(
            # "3 Livro do Tour": quantidade na frente, título depois -- é o
            # formato que o co_parser reconhece (conferido chamando o parser
            # direto). Assim o assistente ABRE com a linha pronta e o tour não
            # precisa digitar dentro de um modal que rola.
            body='<p>3 Livro do Tour</p>',
            message_type='email', subtype_xmlid='mail.mt_comment')

        self.start_tour('/odoo', 'liber_support_venda_tour', login='admin')

        # Perguntar ao BANCO, não ao registro que o teste tem em mãos: o
        # navegador gravou por outra conexão, e um recordset em cache pode
        # responder o que era verdade antes do tour.
        self.env.invalidate_all()
        pedido = self.env['sale.order'].search(
            [('partner_id', '=', partner.id)], limit=1)
        self.assertTrue(pedido, "o tour terminou sem criar o pedido de venda")
        self.assertTrue(pedido.order_line, "o pedido saiu sem linha")
        self.assertFalse(
            self.env['consignment.settlement'].search(
                [('partner_id', '=', partner.id)]),
            "a opção Venda criou uma CO pela tela")
