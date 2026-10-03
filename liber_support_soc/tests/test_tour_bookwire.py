# -*- coding: utf-8 -*-
"""O relatório da Bookwire vira pedido pela tela, com o perfil de quem lança.

O `test_bookwire.py` prova o pedido no ORM. Este prova o caminho: que o
Comercial Assistente com Atendimento abre o chamado, que o botão Importar
reconhece o ZIP, e que o pedido nasce -- ACL faltando, coluna que não
renderiza e botão que sumiu só aparecem aqui.
"""
from odoo.tests import HttpCase, tagged

from .test_bookwire import TOTAL, semear

LOGIN = 'bookwire_tour'


@tagged('post_install', '-at_install')
class TestBookwireTour(HttpCase):

    def test_relatorio_vira_pedido_pela_tela(self):
        dados = semear(self.env)
        company = self.env.company
        grupos = self.env.ref('liber_support.group_support_user')
        comercial = self.env.ref(
            'liber_roles.group_comercial_assistente', raise_if_not_found=False)
        grupos |= comercial or (
            self.env.ref('sales_team.group_sale_salesman_all_leads')
            | self.env.ref('account.group_account_invoice'))
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Faturamento do Tour',
                'login': LOGIN,
                'password': LOGIN,
                'lang': 'en_US',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': [(6, 0, (self.env.ref('base.group_user')
                                      | grupos).ids)],
            })
        # A regra do chamado: o usuário vê os chamados das SUAS equipes.
        dados['equipe'].member_ids = [(4, usuario.id)]
        # O caminho de 27/09/2026 no staging (chamado 2129): o assistente
        # abre com OUTRO anexo -- a planilha convertida à mão, mais nova que
        # o ZIP -- e a pessoa escolhe o ZIP no campo. Escolher relê a grade
        # na tela, e salvar quebrava com "virtual_602". Sem este anexo o tour
        # abria já no ZIP e nunca passava pela releitura.
        self.env['ir.attachment'].create({
            'name': 'bookwire convertido a mao.csv',
            'res_model': dados['chamado']._name,
            'res_id': dados['chamado'].id,
            'raw': b'2;Ebook do Tour\n1;Audiolivro do Tour\n',
        })

        self.start_tour('/odoo', 'liber_support_bookwire_tour', login=LOGIN)

        self.env.invalidate_all()
        pedido = dados['chamado'].sale_order_id
        self.assertTrue(pedido, 'o tour terminou sem criar o pedido')
        self.assertAlmostEqual(pedido.amount_untaxed, TOTAL, places=2)
        self.assertEqual(set(pedido.order_line.mapped('discount')), {0.0})
        self.assertEqual(pedido.client_order_ref, 'Period:08/2026')
