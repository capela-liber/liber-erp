# -*- coding: utf-8 -*-
"""A ponte com o liber_roles: a Amazon é do Comercial.

Pedido da direção em 10/08/2026 — "amazon tem que estar disponível para o
comercial; pense num balanço entre gerente e assistente". O balanço não foi
inventado: este módulo já separava operar de configurar, e a grade da casa
encaixou nessa linha. Ver models/res_groups.py.

Estes testes travam a correspondência. Se alguém trocar os níveis de lado, o
assistente passa a criar conta Amazon e escolher cliente — e isso não faz
barulho nenhum sem um teste.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPonteLiberRoles(TransactionCase):

    def _perfil(self, sufixo):
        return self.env.ref('liber_roles.group_%s' % sufixo,
                            raise_if_not_found=False)

    def setUp(self):
        super().setUp()
        if not self._perfil('direcao'):
            self.skipTest('liber_roles não está instalado nesta base')
        self.operador = self.env.ref('liber_amazon_vendor.group_liber_amazon_user')
        self.gerente = self.env.ref(
            'liber_amazon_vendor.group_liber_amazon_manager')

    def test_o_comercial_alcanca_a_amazon_nos_dois_niveis(self):
        """O pedido, literal."""
        for nivel in ('assistente', 'gerente'):
            self.assertIn(
                self.operador, self._perfil('comercial_%s' % nivel).all_implied_ids,
                'Comercial/%s não alcança a Amazon: a ponte não rodou ou foi '
                'removida' % nivel)

    def test_o_balanco_entre_gerente_e_assistente(self):
        """Onde a linha cai, e por que ela é uma linha e não um degrau só.

        O assistente é o Operator: importa o pedido, corrige o casamento de
        produto, gera a cotação. Não cria conta Amazon nem escolhe cliente —
        o ACL de liber.amazon.account para ele é r1 w0 c0 u0.
        """
        self.assertNotIn(
            self.gerente, self._perfil('comercial_assistente').all_implied_ids,
            'o assistente comercial ganhou o nível de gerente da Amazon: '
            'criar conta e escolher cliente deixou de ser da gerência')
        for sufixo in ('comercial_gerente', 'direcao'):
            self.assertIn(self.gerente, self._perfil(sufixo).all_implied_ids,
                          '%s não administra a Amazon' % sufixo)

    def test_o_assistente_nao_edita_a_conta_amazon(self):
        """A promessa acima, exercitada no ORM em vez de acreditada."""
        from odoo.exceptions import AccessError
        conta = self.env['liber.amazon.account'].search([], limit=1)
        if not conta:
            self.skipTest('esta base não tem conta Amazon cadastrada')
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Comercial Amazon', 'login': 'com.amz@ponte.test',
                'group_ids': [(4, self._perfil('comercial_assistente').id)],
            })
        env = self.env(user=usuario.id, su=False)
        self.assertTrue(env['liber.amazon.account'].browse(conta.id).name,
                        'o assistente não consegue nem ler a conta Amazon')
        with self.assertRaises(AccessError, msg=(
                'o assistente comercial editou a conta Amazon')):
            env['liber.amazon.account'].browse(conta.id).write(
                {'name': 'Conta mexida'})

    def test_a_credencial_nao_e_de_ninguem_da_grade(self):
        """A fronteira que o módulo já traçava e que a ponte não move.

        O refresh token e os campos da conexão são groups="base.group_system"
        no próprio modelo. O gerente cria a conta; o administrador cola o
        token. Nenhuma função da casa vira administrador do sistema.
        """
        for sufixo in ('comercial_assistente', 'comercial_gerente', 'direcao'):
            self.assertNotIn(
                self.env.ref('base.group_system'),
                self._perfil(sufixo).all_implied_ids,
                '%s virou administrador do sistema e passou a ver a '
                'credencial da Amazon' % sufixo)
