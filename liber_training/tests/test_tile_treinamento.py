# -*- coding: utf-8 -*-
"""O tile Treinamento leva aos cursos (03/10/2026).

Na vitrine a conta de demonstração não via os cursos na home: o menu raiz
do eLearning é do grupo Officer, que edita cursos. A porta do aluno é esta —
um menu raiz sem grupo, cuja ação sai do cliente web para /slides.
"""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTileTreinamento(TransactionCase):

    def setUp(self):
        super().setUp()
        self.menu = self.env.ref('liber_training.menu_training_root')
        self.action = self.env.ref('liber_training.action_courses')

    def _menus_de(self, groups):
        LOGIN = 'tile_treino'
        user = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': "Quem assiste", 'login': LOGIN, 'password': LOGIN,
                'group_ids': [(6, 0, groups.ids)]})
        self.env.invalidate_all()
        return self.env['ir.ui.menu'].with_user(user).load_menus(False)

    def test_the_tile_opens_the_courses_in_the_same_tab(self):
        self.assertFalse(self.menu.parent_id, "é tile: menu raiz")
        self.assertTrue(self.menu.web_icon, "sem web_icon a home mostra o cubo")
        self.assertEqual(self.action.type, 'ir.actions.act_url')
        self.assertEqual(self.action.url, '/slides')
        # target="new" é pop-up bloqueado no Chrome headless: o click_all
        # estoura por tempo e o aluno ganha uma aba a mais sem pedir.
        self.assertEqual(self.action.target, 'self')

    def test_a_plain_internal_user_reaches_the_tile(self):
        menus = self._menus_de(self.env.ref('base.group_user'))
        self.assertIn(self.menu.id, menus)

    def test_the_visitor_of_the_showcase_reaches_the_tile(self):
        """O caso que motivou: a conta `demo` da vitrine."""
        visitante = self.env.ref('liber_roles.group_visitante',
                                 raise_if_not_found=False)
        if not visitante:
            self.skipTest('liber_roles não está instalado neste banco')
        menus = self._menus_de(visitante)
        self.assertIn(self.menu.id, menus)

    def test_the_portal_has_no_home_and_no_tile(self):
        LOGIN = 'tile_portal'
        portal = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': "Portal", 'login': LOGIN, 'password': LOGIN,
                'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        self.env.invalidate_all()
        try:
            visiveis = self.env['ir.ui.menu'].with_user(portal).search(
                [('id', '=', self.menu.id)])
        except AccessError:
            visiveis = self.env['ir.ui.menu']   # nem lê menus: dá no mesmo
        self.assertFalse(visiveis, "portal não tem home, logo não tem tile")

    def test_a_group_on_the_menu_would_close_the_door(self):
        """O erro a impedir: o primeiro grupo num menu aberto não soma
        ninguém — subtrai todo o resto (22/08/2026, Compras)."""
        self.assertFalse(self.menu.group_ids, "o tile é de todo usuário interno")
