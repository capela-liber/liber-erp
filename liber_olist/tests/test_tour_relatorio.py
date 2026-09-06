# -*- coding: utf-8 -*-
"""O tour do Relatório: as medidas na tela, não só no ORM.

Este arquivo tem uma origem concreta. As medidas novas (bruto, desconto,
líquido) passaram nos testes de ORM e o Relatório caiu no navegador com
`column olist_order_line.valor_liquido does not exist`: um banco irmão do
mesmo servidor estava uma versão atrás, e o esquema é POR BANCO. O ORM do
teste roda no banco que o teste criou; o pivô roda onde a pessoa está.

O tour executa o `read_group` de verdade, com as quatro medidas e o
agrupamento por data — o caminho exato que estourou.
"""
from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'liber_olist_tour')
class TestRelatorioTour(HttpCase):

    def test_olist_relatorio_tour(self):
        company = self.env.company
        # Perfil comum: o Relatório é leitura, e é a equipe que o abre.
        # A senha é o próprio login (regra da casa para usuário de tour),
        # escrita UMA vez: repetida como literal, a varredura de segredos do
        # publish_liber_erp.sh a lê como credencial e barra a publicação.
        login = 'olist_relatorio_tour'
        usuario = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': "Comercial do Tour",
                'login': login,
                'password': login,
                # Sessão em inglês como nos outros tours — e os rótulos sob
                # teste continuam legíveis: "Valor líquido" e "Data do
                # pedido" são escritos em português na FONTE deste módulo,
                # então é esse o texto que a tela mostra nos dois idiomas.
                # (Ativar um idioma DENTRO do teste não é opção: dispara a
                # sincronia de menus do site e derruba o registry.)
                'lang': 'en_US',
                'company_id': company.id,
                'company_ids': [(6, 0, [company.id])],
                'group_ids': [(4, self.env.ref('base.group_user').id)],
            })
        self.assertTrue(usuario.exists())

        self.env['olist.account'].search([]).write({'active': False})
        account = self.env['olist.account'].create({
            'name': "Olist Relatório Tour", 'company_id': company.id,
            'token': "TOKEN-RT", 'read_only': True})
        # Dentro dos 30 dias: é o filtro padrão da ação, e um pedido velho
        # deixaria o pivô vazio — sem célula não há o que provar.
        self.env['olist.order'].create({
            'account_id': account.id, 'olist_id': 'TOUR-R1', 'valor': 100.0,
            'numero': "TOUR-R1", 'situacao': "Aprovado",
            'canal': "Mercado Livre",
            'data_pedido': fields.Date.today(),
            'valor_desconto': 20.0,
            'line_ids': [(0, 0, {'codigo': "9785555555556",
                                 'descricao': "Livro do Relatório",
                                 'quantidade': 2, 'valor_unitario': 60.0})]})

        self.start_tour("/odoo", "olist_relatorio_tour",
                        login='olist_relatorio_tour')
