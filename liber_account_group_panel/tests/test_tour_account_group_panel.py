# -*- coding: utf-8 -*-
"""A barra lateral pela tela, no perfil de quem usa o Plano de Contas.

Regra da casa (CLAUDE.md, 22/08): ao fechar o módulo, o ORM não basta. Aqui o
usuário do tour é um Contador (`account.group_account_user`), não o admin --
admin passa em tudo e não prova nada sobre o perfil.
"""
from odoo.tests import HttpCase, tagged

from .common import AccountGroupPanelCommon



# A senha do usuário de tour é IGUAL AO LOGIN -- é assim que o `start_tour`
# entra. O literal fica no login e a senha o referencia: escrito das duas
# vezes, ele casa com a varredura de segredos do publish_liber_erp.sh e barra
# a publicação inteira.
LOGIN = 'contador_group_panel'

@tagged('post_install', '-at_install')
class TestAccountGroupPanelTour(AccountGroupPanelCommon, HttpCase):

    def test_account_group_panel_tour(self):
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Contador do Tour',
            'login': LOGIN,
            # A senha é igual ao login: é o que o start_tour usa para entrar.
            'password': LOGIN,
            # Passo que só existe por texto quebra quando a tradução entra.
            'lang': 'en_US',
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])],
            'group_ids': [(4, self.env.ref('account.group_account_user').id)],
        })
        self.start_tour('/odoo', 'account_group_panel_tour',
                        login=LOGIN)
