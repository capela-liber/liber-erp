# -*- coding: utf-8 -*-
"""A grade dos canais de venda.

Aqui não há campo novo nem lógica nova: o que pode quebrar é a herança de view
e a ação. Uma herança que erra a âncora derruba a instalação inteira, e uma
ação sem `list` no `view_mode` deixa a grade invisível sem dar erro nenhum --
que é o modo silencioso de este módulo deixar de fazer o que promete.
"""
from lxml import etree

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


# `post_install`: o teste cria `crm.team`, e este módulo depende só de
# `sales_team`, então roda ANTES do `crm` na ordem de carga. Num banco que já
# tem o `crm` instalado (o `testing`), a coluna `crm_team.alias_id` já existe
# como NOT NULL, mas o mixin que cria o alias ainda não está no registro --
# e o INSERT bate no constraint. Depois de tudo carregado, criar equipe
# funciona normalmente.
@tagged('post_install', '-at_install')
class TestCrmTeamGrid(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acao = cls.env.ref('sales_team.crm_team_action_sales')
        cls.equipe = cls.env['crm.team'].create({'name': 'Livrarias de Teste'})
        # As empresas são as que o banco já tem, e não empresas novas: com o
        # `account` instalado, `res.company.create` esbarra no NOT NULL de
        # `fiscalyear_last_day` (o campo é delegado à empresa raiz e não entra
        # no INSERT). Reaproveitar não custa nada aqui -- o que se testa é a
        # grade, não a criação de empresa.
        cls.empresas = cls.env['res.company'].search([], order='id')

    def _arch_da_lista(self):
        """O arch já resolvido, com as heranças aplicadas -- é o que a tela vê."""
        arch = self.env['crm.team'].get_view(view_type='list')['arch']
        return etree.fromstring(arch)

    def test_acao_abre_a_lista(self):
        """Sem `list` no view_mode a grade não existe para o usuário."""
        self.assertIn('list', self.acao.view_mode.split(','))

    def test_lista_e_a_primeira(self):
        """A ação existe para arrumar as equipes: a grade é a tela de entrada."""
        self.assertEqual(self.acao.view_mode.split(',')[0], 'list')

    def test_kanban_e_form_continuam(self):
        """Acrescentar a grade não pode custar as telas que já existiam."""
        modos = self.acao.view_mode.split(',')
        self.assertIn('kanban', modos)
        self.assertIn('form', modos)

    def test_colunas_pedidas(self):
        """Equipe, empresa e quem vende -- as três perguntas da tarefa.

        `company_id` fica atrás de `base.group_multi_company` (herdado do
        `sales_team`), então o arch tem que trazê-lo para quem enxerga mais de
        uma editora; é o caso de quem monta os times.
        """
        arch = self._arch_da_lista()
        campos = arch.xpath('//field/@name')
        for campo in ('name', 'company_id', 'user_id', 'member_ids'):
            self.assertIn(campo, campos, "a coluna %s sumiu da grade" % campo)

    def test_grade_e_digitavel(self):
        """`editable` é o que separa uma grade de uma lista de consulta."""
        arch = self._arch_da_lista()
        self.assertEqual(arch.get('editable'), 'bottom')

    def test_edicao_em_bloco(self):
        """Vem do `sales_team`, mas é requisito daqui: se sair, a grade perde a razão."""
        arch = self._arch_da_lista()
        self.assertEqual(arch.get('multi_edit'), '1')

    def test_nome_deixou_de_ser_somente_leitura(self):
        """Renomear equipe é metade do trabalho de organizar as equipes."""
        arch = self._arch_da_lista()
        (nome,) = arch.xpath('//field[@name="name"]')
        self.assertNotEqual(
            nome.get('readonly'), '1',
            "o `readonly` do sales_team voltou: não dá para renomear na grade")

    def test_edicao_em_bloco_grava(self):
        """O caminho feliz do multi_edit: escrever em várias de uma vez.

        A tela manda um `write` só para o conjunto -- é esse comportamento que
        interessa, e ele tem que valer para os campos da grade.
        """
        outra = self.env['crm.team'].create({'name': 'Redes de Teste'})
        empresa = self.empresas[0]
        equipes = self.equipe | outra

        equipes.write({'company_id': empresa.id})

        self.assertEqual(equipes.mapped('company_id'), empresa)

    def test_vendedor_de_outra_empresa_nao_entra(self):
        """O caso de erro: membro tem que enxergar a empresa da equipe.

        O `sales_team` barra isso com `UserError`, e a grade não pode dar um
        jeito de burlar: se passasse, o time nasceria com alguém que não vê os
        pedidos dele. Vale mais aqui do que em qualquer outro lugar, porque
        preencher empresa e vendedores EM BLOCO é justamente onde se erra sem
        perceber -- trinta linhas de uma vez.
        """
        if len(self.empresas) < 2:
            self.skipTest("precisa de duas empresas no banco")
        empresa_a, empresa_b = self.empresas[0], self.empresas[1]
        self.equipe.company_id = empresa_a
        forasteiro = self.env['res.users'].create({
            'name': 'Vendedor da B',
            'login': 'vendedor_b_teste',
            'company_id': empresa_b.id,
            'company_ids': [(6, 0, [empresa_b.id])],
        })

        with self.assertRaises(UserError), self.cr.savepoint():
            self.equipe.member_ids = forasteiro
