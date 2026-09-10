# -*- coding: utf-8 -*-
"""O aplicar modelo, na tela, com o perfil de quem usa.

Escrito depois de o dono dizer "não está dando pra aplicar modelo" enquanto
os testes de ORM do mesmo caminho passavam verdes. É a regra da casa em
estado puro: o ORM mede o que o teste pediu, e a tela pede mais -- o direito
de LER event.fair.template (que o assistente precisa e o ACL pode não ter
dado), o botão renderizado dentro da aba, o diálogo, o autocompletar e a
linha aparecendo na grade depois.

O usuário do tour NÃO é o admin: admin passa em tudo e não prova nada sobre
o perfil.
"""
from datetime import date, timedelta

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs_tour')
class TestTourAplicarModelo(HttpCase):

    def test_aplicar_modelo_na_tela(self):
        company = self.env.company
        papel = self.env.ref('liber_roles.group_comercial_gerente',
                             raise_if_not_found=False)
        grupos = [(4, self.env.ref('liber_fairs.group_fair_manager').id)]
        if papel:
            grupos.append((4, papel.id))
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Comercial do Tour',
                'login': 'feira_tour',
                'password': 'feira_tour',
                # os passos do tour casam com os rótulos em português
                'lang': 'pt_BR',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': grupos,
            })
        livro = self.env['product.product'].create({
            'name': 'Livro do Tour', 'type': 'consu', 'is_storable': True})
        self.env['event.fair.template'].create({
            'name': 'Modelo do Tour',
            'company_id': company.id,
            'line_ids': [(0, 0, {'product_id': livro.id, 'qty_planned': 3})],
        })
        hoje = date.today()
        self.env['event.fair'].create({
            'name': 'Feira do Modelo',
            'date_start': hoje,
            'date_end': hoje + timedelta(days=1),
            'company_id': company.id,
        })
        self.start_tour('/odoo', 'fair_apply_template_tour',
                        login='feira_tour')
        feira = self.env['event.fair'].search(
            [('name', '=', 'Feira do Modelo')], limit=1)
        self.assertIn(livro, feira.line_ids.mapped('product_id'),
                      "O modelo aplicado na tela tem de ter entrado na grade")
