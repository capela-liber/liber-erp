# -*- coding: utf-8 -*-
"""A ficha de contato, perfil por perfil (22/08/2026).

"Me diga o que cada perfil acessa dos contatos." A matriz de ACL responde o
que cada um PODE; este teste responde o que a TELA faz com isso -- que é onde
o direito de ler vira, ou não, uma ficha que abre.

O mesmo tour roda uma vez por papel. Ele é curto de propósito: abrir o app,
abrir um contato, ler a ficha. Tour longo falharia adiante por motivo que nada
tem a ver com o papel, e o que se quer medir aqui é a porta.
"""
from odoo.tests import HttpCase, tagged

PAPEIS = [
    'comercial_assistente', 'comercial_gerente',
    'logistica_assistente', 'logistica_gerente',
    'financeiro_assistente', 'financeiro_gerente',
    'editorial_assistente', 'editorial_gerente',
    'juridico_assistente', 'juridico_gerente',
    'marketing_assistente', 'marketing_gerente',
    'direcao', 'visitante',
]


@tagged("post_install", "-at_install", "liber_roles_tour")
class TestContatosPorPerfil(HttpCase):

    def _usuario(self, papel):
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Diag %s' % papel,
            'login': 'tour_%s' % papel,
            'password': 'tour_%s' % papel,
            'lang': 'en_US',
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, [self.env.company.id])],
            'group_ids': [(4, self.env.ref('liber_roles.group_%s' % papel).id)],
        })

    def test_a_ficha_de_contato_abre_para_todo_perfil(self):
        """Ler contato é de todos: nenhum perfil da casa pode ficar de fora.

        O contato é o registro mais atravessado do ERP -- cliente, fornecedor,
        autor, livraria, transportadora. Um papel que não abre a ficha não
        consegue trabalhar, e é por isso que o ACL dá leitura a todos. Aqui se
        prova que a TELA cumpre o que o ACL promete, para cada um.
        """
        self.env['res.partner'].create({
            'name': 'Contato do Tour', 'is_company': True,
            'email': 'contato.tour@liber.test',
        })
        quebrados = []
        for papel in PAPEIS:
            self._usuario(papel)
            try:
                self.start_tour("/odoo", "contatos_tour",
                                login='tour_%s' % papel)
            except AssertionError as e:
                quebrados.append((papel, str(e).splitlines()[0][:120]))
        self.assertFalse(
            quebrados,
            "a ficha de contato não abriu para: %s" % "; ".join(
                "%s (%s)" % (p, m) for p, m in quebrados))
