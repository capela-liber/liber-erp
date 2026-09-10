# -*- coding: utf-8 -*-
"""O caminho do Comercial Gerente pelos grupos econômicos, na tela real.

O ORM prova o compute e o ACL; o tour prova a chegada: o menu de
configuração abre para o perfil, o formulário do grupo lista os membros, e
a ficha da loja desenha a Razão Social e o Grupo econômico. É a classe de
defeito que só a tela pega -- a lição do Access Error do Editorial.

O usuário é do perfil real (Comercial Gerente do liber_roles), nunca o
admin: admin passa em tudo e não prova nada.
"""
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "partner_group_tour")
class TestPartnerGroupTour(HttpCase):

    def _usuario_comercial(self):
        gerente = self.env.ref('liber_roles.group_comercial_gerente',
                               raise_if_not_found=False)
        if not gerente:
            self.skipTest("liber_roles não está neste banco; o tour do "
                          "perfil comercial não tem o que provar sem ele")
        company = self.env.company
        return self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Comercial do Tour',
                'login': 'comercial_tour',
                'password': 'comercial_tour',
                # Em inglês pelo motivo dos outros tours da casa: passo que
                # só existe por texto quebra quando a tradução entra.
                'lang': 'en_US',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, gerente.id)],
            })

    def _cenario(self):
        grupo = self.env['liber.partner.group'].create({
            'name': 'Travessa do Tour', 'cnpj_roots': '31.999.999'})
        loja = self.env['res.partner'].create({
            'name': 'Travessa do Tour Botafogo',
            'legal_name': 'LIVRARIA DO TOUR LTDA',
            'vat': '31.999.999/0001-01',
        })
        # O vínculo veio da raiz, não da mão: é o caminho que o tour percorre.
        self.assertEqual(loja.partner_group_id, grupo)
        return grupo, loja

    def test_tour_configuracao_dos_grupos(self):
        self._cenario()
        self._usuario_comercial()
        self.start_tour("/odoo", "partner_group_config_tour",
                        login="comercial_tour")

    def test_tour_ficha_da_loja(self):
        _grupo, loja = self._cenario()
        self._usuario_comercial()
        self.start_tour(
            "/odoo/action-base.action_partner_form/%d" % loja.id,
            "partner_group_ficha_tour", login="comercial_tour")
