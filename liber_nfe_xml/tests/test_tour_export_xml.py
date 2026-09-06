# -*- coding: utf-8 -*-
"""O tour da exportação: a porta, pela tela de verdade.

O `test_export_wizard.py` prova o CONTEÚDO do pacote no ORM. Este prova o
caminho: que o assistente abre para um usuário comum, que a lista de meses
renderiza com as suas caixas, e que marcar um mês e apertar Exportar devolve um
arquivo em vez de um erro de acesso. É a diferença entre "tem direito" e
"chega lá" -- e é o tipo de coisa que só a tela conta.
"""
import base64

from odoo.tests import HttpCase, tagged

from .test_nfe_xml import KEY_1, nfe_xml


@tagged("post_install", "-at_install", "nfe_xml_tour")
class TestExportXmlTour(HttpCase):

    def test_export_xml_tour(self):
        company = self.env.company
        # Sem admin de propósito: admin passa em tudo e não prova nada sobre o
        # perfil de quem vai usar isto. Senha igual ao login, como manda a casa.
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Fiscal do Tour',
                'login': 'export_xml_tour',
                'password': 'export_xml_tour',
                'lang': 'en_US',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, self.env.ref('base.group_user').id)],
            })
        self.assertTrue(usuario.exists())

        # Sem nota não há mês, e sem mês a lista abre vazia: o tour não teria
        # o que marcar.
        self.env['nfe.xml.panel'].create({
            'key': KEY_1,
            'file': base64.b64encode(nfe_xml(KEY_1)),
            'file_name': '%s-nfe.xml' % KEY_1,
            'file_create_date': '2026-03-10',
            'nfe_direction': 'out',
            'company_id': company.id,
            'status': 'valid',
        })

        self.start_tour("/odoo", "nfe_xml_export_tour", login="export_xml_tour")
