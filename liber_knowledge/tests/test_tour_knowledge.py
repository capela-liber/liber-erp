# -*- coding: utf-8 -*-
"""O tour do wiki: um usuário interno comum lê um manual, pela tela.

O `test_liber_manuals.py` prova no ORM que o interno lê e o portal não. Este
prova o caminho na tela "Manuais": o mapa abre para esse perfil, o manual
aparece com as capturas, o link para outro manual abre ali mesmo, a busca acha
pelo texto, e os botões de edição não aparecem para quem só lê.
"""
from odoo.tests import HttpCase, tagged

LOGIN = 'wiki_tour'


@tagged('post_install', '-at_install', 'liber_knowledge_tour')
class TestKnowledgeTour(HttpCase):

    def test_knowledge_tour(self):
        company = self.env.company
        # Só base.group_user: o que se prova é que ler o wiki não pede grupo
        # nenhum além de ser usuário interno. Sessão em inglês, como os demais
        # tours da casa; o texto buscado é conteúdo e não se traduz.
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Leitor do Wiki',
            'login': LOGIN,
            'password': LOGIN,
            'lang': 'en_US',
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.assertTrue(self.env['document.page'].search_count(
            [('liber_manual_slug', '=', 'liber_soc_settlement')]))
        self.start_tour('/odoo/manuais', 'liber_knowledge_tour', login=LOGIN)
