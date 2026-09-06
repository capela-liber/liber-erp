# -*- coding: utf-8 -*-
"""Tour do orçamento, no PERFIL de quem usa.

Regra da casa (22/08): ao fechar um assunto, o teste de ORM não basta -- ele
mede o que o teste pediu, e a tela mede o que a tela pede. Aqui prova-se que o
app existe para o grupo do orçamento (e não só para o admin), que o formulário
abre e que a coluna Practical renderiza na linha.
"""
from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestTourBudget(HttpCase):

    def test_tour_perfil_orcamento(self):
        company = self.env.company
        posicao = self.env['budget.position'].create({'name': 'Tour Pos'})
        orc = self.env['budget.analytic'].create({
            'name': 'Tour Budget', 'date_from': '2020-01-01',
            'date_to': '2020-12-31', 'company_id': company.id,
        })
        self.env['budget.line'].create({
            'budget_analytic_id': orc.id, 'position_id': posicao.id,
            'budget_amount': -500,
            'date_from': orc.date_from, 'date_to': orc.date_to,
        })
        # O usuário do tour nasce com a SENHA igual ao login e com o perfil que
        # se quer provar -- nunca o admin, que passa em tudo e não prova nada.
        self.env['res.users'].create({
            'name': 'tour_budget', 'login': 'tour_budget',
            'password': 'tour_budget',
            'company_id': company.id,
            'company_ids': [Command.set([company.id])],
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('liber_budget.group_budget_manager').id,
            ])],
        })
        self.start_tour('/odoo', 'liber_budget_consolidado_tour',
                        login='tour_budget')
