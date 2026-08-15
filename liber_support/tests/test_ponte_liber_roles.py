# -*- coding: utf-8 -*-
"""A ponte com o liber_roles: o Atendimento aparece para o Comercial.

Pedido da direção em 10/08/2026. A concessão mora neste módulo, e não no
liber_roles, porque o liber_roles roda em prod/staging/liber/testing e o
atendimento só no testing -- uma linha lá viraria dependência de módulo e o
próximo -u em produção iria querer instalar o atendimento inteiro. Ver
models/res_groups.py.

Estes testes são o freio da inversão: se alguém "simplificar" mudando a
concessão de lado, o -u em produção passa a arrastar um app; se alguém apagar
a ponte, o Comercial perde o Atendimento em silêncio.
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
        self.suporte = self.env.ref('liber_support.group_support_user')

    def test_o_comercial_ve_o_atendimento_nos_dois_niveis(self):
        """O pedido, literal -- e o Gerente entra por herança, não por linha.

        A ponte concede só ao Assistente de propósito: o Gerente o implica.
        Escrever as duas seria criar uma aresta redundante, e aresta neste
        repositório entra fácil e só sai com um (3, ...) explícito.
        """
        for nivel in ('assistente', 'gerente'):
            perfil = self._perfil('comercial_%s' % nivel)
            self.assertIn(
                self.suporte, perfil.all_implied_ids,
                'Comercial/%s não alcança o Atendimento: a ponte do '
                'liber_support não rodou ou foi removida' % nivel)

    def test_a_direcao_acompanha(self):
        """A régua do liber_roles: a Direção alcança tudo que a casa alcança.

        Não é generosidade -- é o que impede o teste de superconjunto de lá
        (test_acessos.test_direcao_alcanca_tudo_que_a_casa_alcanca) de ficar
        vermelho apontando para este módulo.
        """
        self.assertIn(self.suporte, self._perfil('direcao').all_implied_ids,
                      'a Direção ficou sem o Atendimento e deixou de ser '
                      'superconjunto da casa')

    def test_o_visitante_continua_de_fora(self):
        """Decisão registrada no NOTES §4: atendimento é conversa de cliente,
        não vitrine. A conta pública circula.
        """
        visitante = self._perfil('visitante')
        if not visitante:
            self.skipTest('sem conta de visitante nesta base')
        self.assertNotIn(
            self.suporte, visitante.all_implied_ids,
            'o Atendimento entrou na conta pública de demonstração')

    def test_o_gerente_administra_e_o_atendente_nao(self):
        """A régua da direção (10/08/2026), e ela cai onde os ACLs cortam.

        "O gerente comercial administra o atendimento, mas o atendente
        responde e muda de fase e outras coisas que são de um assistente."
        Traduzido: o Assistente fica no `group_support_user`, que grava o
        chamado e apenas LÊ equipes e selos; o Gerente sobe para o
        `group_support_manager`, que cria e edita equipe, selo e as horas de
        SLA.

        O outro lado é o que faz disto uma régua: se o atendente ganhar o
        nível de gerente, o departamento vira um nível só e ninguém percebe.
        """
        gerente = self.env.ref('liber_support.group_support_manager')
        for sufixo in ('comercial_gerente', 'direcao'):
            self.assertIn(
                gerente, self._perfil(sufixo).all_implied_ids,
                '%s não administra o Atendimento' % sufixo)
        self.assertNotIn(
            gerente, self._perfil('comercial_assistente').all_implied_ids,
            'o atendente ganhou o nível de gerente do Atendimento: configurar '
            'equipe, selo e SLA deixou de ser da gerência')

    def test_o_atendente_move_o_chamado_mas_nao_cria_fase(self):
        """A promessa acima, exercitada no ORM em vez de acreditada.

        `has_group` prova que o grupo está lá; só a escrita prova que o corte
        entre "responder" e "configurar" é onde a direção disse que era.
        """
        Users = self.env['res.users'].with_context(no_reset_password=True)
        atendente = Users.create({
            'name': 'Atendente comercial', 'login': 'atendente@ponte.test',
            'group_ids': [(4, self._perfil('comercial_assistente').id)],
        })
        env = self.env(user=atendente.id, su=False)

        equipe = self.env['liber.support.team'].search([], limit=1)
        if not equipe:
            self.skipTest('esta base não tem equipe de atendimento')
        fases = self.env['liber.support.stage'].search([], order='sequence')
        if len(fases) < 2:
            self.skipTest('esta base não tem duas fases de atendimento')

        # Atendente sem equipe não é um cenário: a `rule_support_ticket_user`
        # recorta os chamados às equipes de que a pessoa participa (ou aos
        # atribuídos a ela). Sem esta linha o teste mediria a regra de
        # registro, não a régua de níveis que ele diz medir.
        equipe.sudo().member_ids = [(4, atendente.id)]

        chamado = env['liber.support.ticket'].create({
            'name': 'Chamado do atendente', 'team_id': equipe.id,
            'stage_id': fases[0].id})
        chamado.write({'stage_id': fases[1].id})
        self.assertEqual(chamado.stage_id, fases[1],
                         'o atendente não conseguiu mudar a fase do chamado')

        from odoo.exceptions import AccessError
        with self.assertRaises(AccessError, msg=(
                'o atendente criou uma fase de atendimento: isso é '
                'configuração, e configuração é do gerente')):
            env['liber.support.stage'].create(
                {'name': 'Fase proibida', 'sequence': 99})
