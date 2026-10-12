# -*- coding: utf-8 -*-
"""O Editorial encurta um link em edlab.press/r, pela tela de verdade.

"O editorial assistente e gerente precisa estar habilitado a encurtar um link
em edlab.press/r. Hoje apenas o Paulo" (08/10/2026). O `test_acessos.py`
prova o menu e o ACL no ORM. Este prova o caminho: a lista abre, o botão Novo
existe, o formulário aceita o link e, salvo, mostra o código curto.

O par importa aqui mais que de costume: a porta de 11/08 estava aberta e a
lista continuava atrás do modo debug, e o ACL do core no 19 dá só leitura ao
usuário interno. Nenhum dos dois buracos aparece num teste que cria o registro
pelo ORM como administrador.
"""
from odoo.tests import HttpCase, tagged

#: login e senha do usuário de tour; literal, a senha o referencia (ver
#: CLAUDE.md: senha em CONSTANTE, senão a varredura do publish barra).
LOGIN = 'editorial_link_tour'

URL_DO_TOUR = 'https://edlab.press/catalogo/livro-do-tour'


@tagged("post_install", "-at_install", "liber_roles_tour")
class TestEditorialLinkCurtoTour(HttpCase):

    def test_editorial_encurta_um_link(self):
        company = self.env.company
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Editorial do Tour (links)',
                'login': LOGIN,
                'password': LOGIN,
                'lang': 'en_US',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, self.env.ref(
                    'liber_roles.group_editorial_assistente').id)],
            })
        self.assertTrue(usuario.exists())

        self.start_tour("/odoo", "editorial_link_curto_tour", login=LOGIN)

        # O que a tela gravou, lido de volta: o link é do usuário do tour e
        # tem o código que vira /r/<código>.
        link = self.env['link.tracker'].search([('url', '=', URL_DO_TOUR)])
        self.assertEqual(len(link), 1, 'o tour salvou %d links' % len(link))
        self.assertEqual(link.create_uid, usuario)
        self.assertTrue(link.link_code_ids, 'o link nasceu sem código curto')
        self.assertIn('/r/%s' % link.code, link.short_url)
