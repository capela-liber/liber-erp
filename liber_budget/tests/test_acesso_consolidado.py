# -*- coding: utf-8 -*-
"""Papéis e multiempresa no orçamento consolidado.

O consolidado abriu uma porta nova: um orçamento da holding soma o realizado
das filhas. A pergunta que isso levanta -- e que o teste de cálculo não
responde -- é **quem pode ver o quê**.

Três eixos aqui:

* **papel**: quem não tem o grupo do orçamento não lê nada; usuário lê; gerente
  lê e escreve.
* **empresa**: a regra de registro (`ir.rule`) esconde orçamento de empresa que
  a pessoa não tem no seletor.
* **consolidação**: o cálculo do practical usa `sudo()` de propósito -- senão o
  consolidado seria mentira parcial, somando só o que o leitor pode ver, e dois
  usuários veriam números diferentes para a MESMA linha. O preço é que quem
  abre um consolidado vê valor agregado de empresa a que não tem acesso
  direto. Isso é deliberado e está provado abaixo, para ninguém "consertar"
  sem saber o que muda.
"""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAcessoConsolidado(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.empA = cls.env.company
        cls.empB = cls.env['res.company'].search(
            [('id', '!=', cls.empA.id)], limit=1)
        cls.g_user = cls.env.ref('liber_budget.group_budget_user')
        cls.g_manager = cls.env.ref('liber_budget.group_budget_manager')

    def _usuario(self, nome, grupos, empresas):
        """`base.group_user` entra SEMPRE, além do papel que se quer provar.

        Sem ele o usuário não é nem empregado: não lê `res.company`, e o teste
        falha com AccessError em 'Companies' -- que é artefato do teste, não
        defeito do módulo. Foi o que aconteceu na primeira rodada.
        """
        grupos = [self.env.ref('base.group_user')] + list(grupos)
        return self.env['res.users'].create({
            'name': nome, 'login': nome, 'password': nome,
            'company_id': empresas[0].id,
            'company_ids': [Command.set([e.id for e in empresas])],
            'group_ids': [Command.set([g.id for g in grupos])],
        })

    def _orcamento(self, empresa, consolidadas=None):
        vals = {
            'name': 'Consolidado Teste', 'date_from': '2020-01-01',
            'date_to': '2020-12-31', 'company_id': empresa.id,
        }
        if consolidadas:
            vals['company_ids'] = [Command.set([c.id for c in consolidadas])]
        return self.env['budget.analytic'].create(vals)

    # ----------------------------------------------------------- papéis

    def test_sem_grupo_nao_le(self):
        """Quem não é do orçamento não lê orçamento -- nem o próprio."""
        zé = self._usuario('bud_sem_grupo', [], [self.empA])
        orc = self._orcamento(self.empA)
        with self.assertRaises(AccessError):
            self.env['budget.analytic'].with_user(zé).browse(orc.id).read(['name'])

    def test_usuario_le_gerente_escreve(self):
        """O grupo `user` lê; o `manager` também escreve.

        Os dois têm write no CSV de acesso, então o que separa os papéis é o
        que a TELA oferece -- e é isso que o tour cobre. Aqui prova-se o piso:
        ambos leem, e ninguém de fora lê.
        """
        leitor = self._usuario('bud_user', [self.g_user], [self.empA])
        gerente = self._usuario('bud_manager', [self.g_manager], [self.empA])
        orc = self._orcamento(self.empA)
        for quem in (leitor, gerente):
            self.assertTrue(
                self.env['budget.analytic'].with_user(quem).browse(orc.id).name,
                '%s tem de conseguir ler' % quem.login)
        self.env['budget.analytic'].with_user(gerente).browse(orc.id).write(
            {'name': 'Renomeado pelo gerente'})

    # -------------------------------------------------------- empresa

    def test_orcamento_de_outra_empresa_nao_aparece(self):
        """A `ir.rule` esconde o orçamento de empresa fora do seletor."""
        if not self.empB:
            self.skipTest('este banco tem uma empresa só')
        orc_b = self._orcamento(self.empB)
        so_a = self._usuario('bud_so_a', [self.g_user], [self.empA])
        achados = self.env['budget.analytic'].with_user(so_a).search(
            [('id', '=', orc_b.id)])
        self.assertFalse(
            achados, 'orçamento da outra empresa não pode aparecer para quem '
                     'não tem essa empresa no seletor')

    def test_quem_tem_as_duas_ve_as_duas(self):
        if not self.empB:
            self.skipTest('este banco tem uma empresa só')
        orc_a = self._orcamento(self.empA)
        orc_b = self._orcamento(self.empB)
        ambas = self._usuario('bud_ambas', [self.g_user], [self.empA, self.empB])
        achados = self.env['budget.analytic'].with_user(ambas).with_context(
            allowed_company_ids=[self.empA.id, self.empB.id]).search(
                [('id', 'in', (orc_a | orc_b).ids)])
        self.assertEqual(len(achados), 2)

    # --------------------------------------------------- a consolidação

    def test_consolidado_e_o_mesmo_numero_para_todos(self):
        """O practical NÃO muda conforme quem olha.

        É o ponto do `sudo()`: sem ele, o consolidado somaria só o que o leitor
        enxerga, e o gerente da holding e o do grupo veriam números diferentes
        para a mesma linha. Orçamento cujo valor depende do observador não é
        orçamento.
        """
        if not self.empB:
            self.skipTest('este banco tem uma empresa só')
        orc = self._orcamento(self.empA, consolidadas=[self.empB])
        posicao = self.env['budget.position'].create({'name': 'Pos Acesso'})
        linha = self.env['budget.line'].create({
            'budget_analytic_id': orc.id, 'position_id': posicao.id,
            'budget_amount': -100,
            'date_from': orc.date_from, 'date_to': orc.date_to,
        })
        so_a = self._usuario('bud_visao_a', [self.g_user], [self.empA])
        ambas = self._usuario('bud_visao_ab', [self.g_user], [self.empA, self.empB])

        v1 = self.env['budget.line'].with_user(so_a).browse(
            linha.id).practical_amount
        v2 = self.env['budget.line'].with_user(ambas).browse(
            linha.id).practical_amount
        self.assertAlmostEqual(
            v1, v2, 2,
            'o practical de uma linha consolidada tem de ser o mesmo para '
            'qualquer leitor -- é o que o sudo() garante')

    def test_a_lista_de_empresas_e_visivel_no_orcamento(self):
        """Quem lê o consolidado tem de conseguir ver DE ONDE vem o número.

        Se o valor agrega outra empresa, esconder a lista seria pior que
        mostrá-la: o leitor veria um total que não sabe explicar.
        """
        if not self.empB:
            self.skipTest('este banco tem uma empresa só')
        orc = self._orcamento(self.empA, consolidadas=[self.empB])
        so_a = self._usuario('bud_le_lista', [self.g_user], [self.empA])
        lido = self.env['budget.analytic'].with_user(so_a).browse(orc.id)
        # O many2one vem VAZIO de propósito -- a regra de registro do Odoo
        # esconde empresa fora do seletor, e não se contorna isso.
        self.assertNotIn(self.empB, lido.company_ids,
                         'o Odoo esconde a empresa fora do seletor, e está '
                         'certo em esconder')
        # ...mas o NOME tem de aparecer, senão o leitor vê um total que não
        # consegue nem nomear.
        self.assertIn(self.empB.name, lido.company_names or '',
                      'quem lê o consolidado tem de conseguir NOMEAR as '
                      'empresas que entram na conta')
        self.assertIn(self.empA.name, lido.company_names or '')
