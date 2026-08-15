# -*- coding: utf-8 -*-
"""A contabilidade analítica pertence a três funções, não à casa inteira.

Sem ``analytic.group_analytic_accounting`` os menus e lançamentos analíticos
simplesmente não existem na tela -- foi a caça ao "cadê o analítico" de
06/08/2026. A chave de Definições resolveria ligando o grupo para TODO
usuário interno; a régua da casa é mais estreita: Direção, Financeiro
Gerente e Jurídico Gerente carregam o grupo pela própria função (fechar
período de royalty é ler o extrato analítico), e os demais seguem sem ver
contabilidade analítica nenhuma."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_roles')
class TestAnaliticaNosRoles(TransactionCase):

    def _implied_tree(self, xmlid):
        group = self.env.ref(xmlid)
        seen = self.env['res.groups']
        frontier = group
        while frontier:
            seen |= frontier
            frontier = frontier.implied_ids - seen
        return seen

    def test_direcao_financeiro_e_juridico_gerente_veem_o_analitico(self):
        analitica = self.env.ref('analytic.group_analytic_accounting')
        for funcao in ('liber_roles.group_direcao',
                       'liber_roles.group_financeiro_gerente',
                       'liber_roles.group_juridico_gerente'):
            self.assertIn(analitica, self._implied_tree(funcao),
                          "%s deve carregar a contabilidade analítica" % funcao)

    def test_os_demais_nao_ganham_o_analitico_de_carona(self):
        analitica = self.env.ref('analytic.group_analytic_accounting')
        for funcao in ('liber_roles.group_juridico_assistente',
                       'liber_roles.group_financeiro_assistente',
                       'liber_roles.group_comercial_gerente',
                       'liber_roles.group_editorial_gerente'):
            self.assertNotIn(analitica, self._implied_tree(funcao),
                             "%s não deve carregar a contabilidade analítica"
                             % funcao)
