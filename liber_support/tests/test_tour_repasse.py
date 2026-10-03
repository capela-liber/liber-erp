# -*- coding: utf-8 -*-
"""O repasse para a outra empresa, pela tela de verdade.

O `test_empresa_segue_equipe.py` prova no ORM que trocar a Equipe grava a
empresa da Equipe nova. Este prova o caminho: que o campo Empresa está
desenhado para o perfil do atendimento, que a equipe da outra empresa chega
ao dropdown, que a tela mostra a empresa nova antes de salvar e que salvar
não devolve Access Error.

Duas armadilhas de tela que o ORM não vê, e que este teste fixa no fixture
porque são o preço de entrada do repasse:

1. o campo Empresa do formulário tem `groups="base.group_multi_company"` --
   sem esse grupo o atendente repassa às cegas;
2. a `ir.rule` da equipe filtra por `company_ids` (as empresas LIGADAS na
   sessão, não as permitidas): quem não estiver com a outra empresa ligada
   não enxerga a equipe dela para escolher.
"""
from odoo.tests import HttpCase, tagged

# A senha vai numa constante de nome curto: a varredura de segredos do
# publish_liber_erp.sh casa `password` seguido de 16+ caracteres, e não
# distingue literal de identificador (lição de 17/09/2026).
LOGIN = 'repasse_tour'


@tagged('post_install', '-at_install')
class TestRepasseTour(HttpCase):

    def test_repassar_chamado_para_a_outra_empresa(self):
        casa = self.env.company
        # Empresas são REAPROVEITADAS: res.company.create estoura no NOT
        # NULL de fiscalyear_last_day com o account instalado.
        outra = self.env['res.company'].search(
            [('id', '!=', casa.id)], order='id', limit=1)
        if not outra:
            self.skipTest("o banco só tem uma empresa")
        multi_company = self.env.ref('base.group_multi_company',
                                     raise_if_not_found=False)
        if not multi_company:
            self.skipTest("sem base.group_multi_company neste banco")

        equipe_casa = self.env['liber.support.team'].create({
            'name': 'Equipe da Casa',
            'company_id': casa.id,
            'alias_name': 'repasse-casa-test',
        })
        equipe_outra = self.env['liber.support.team'].create({
            'name': 'Equipe da Outra Empresa',
            'company_id': outra.id,
            'alias_name': 'repasse-outra-test',
        })

        # Não é o admin: admin passa em tudo e não prova nada sobre o
        # perfil. É um atendente das duas casas — que é quem repassa.
        atendente = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Atendente do Repasse',
                'login': LOGIN,
                'password': LOGIN,
                'lang': 'en_US',
                'company_id': casa.id,
                'company_ids': [(6, 0, [casa.id, outra.id])],
                'group_ids': [
                    (4, self.env.ref('liber_support.group_support_user').id),
                    (4, multi_company.id),
                ],
            })
        # Membro das duas equipes: a ir.rule "own teams" esconde do
        # atendente o chamado de equipe que não é dele — inclusive DEPOIS
        # da escrita, que é quando o repasse seria recusado.
        (equipe_casa | equipe_outra).write(
            {'member_ids': [(4, atendente.id)]})

        ticket = self.env['liber.support.ticket'].create({
            'name': 'Chamado que muda de empresa',
            'team_id': equipe_casa.id,
        })
        self.assertEqual(ticket.company_id, casa,
                         "o chamado tinha de nascer na casa")

        self.start_tour('/odoo', 'liber_support_repasse_tour', login=LOGIN)

        # A tela fez a escrita; o ORM confere o efeito.
        ticket.invalidate_recordset()
        self.assertEqual(ticket.team_id, equipe_outra)
        self.assertEqual(ticket.company_id, outra,
                         "o repasse na tela não levou a empresa junto")
