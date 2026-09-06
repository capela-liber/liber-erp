# -*- coding: utf-8 -*-
"""O "Importar" da CO pela tela, no perfil de quem vai usar.

Regra de 22/08/2026: ao fechar um caminho, o teste de ORM não basta — ele mede
o que o teste pediu, e a tela mede o que a tela pede. Aqui há dois riscos que
só o clique acusa:

* **o ACL.** O assistente nasceu com acesso apenas para o `group_support_user`
  do Atendimento, e quem opera consignação pode não ser do Atendimento. Este
  teste loga como COMERCIAL — `group_soc_user` mais Vendas, que é o que o
  `liber_roles` dá ao Comercial/Assistente — e não como admin: admin passa em
  tudo e não prova nada sobre o perfil. Foi assim que o ACL do assistente
  ganhou a segunda linha no `ir.model.access.csv`.
* **o botão herdado.** Ele entra por `position="after"` num botão do
  `liber_soc_settlement`; renomeado lá, a view quebra na carga e nenhum teste
  de Python percebe.

O módulo não depende do `liber_roles` (e não pode: o `liber_roles` está nos
quatro bancos e este, não), então o perfil é montado aqui com os grupos que
o Comercial recebe lá.
"""
from markupsafe import Markup

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestImportNaCoTour(HttpCase):

    def test_importar_na_co_pela_tela(self):
        company = self.env.company
        # A senha é o próprio login, regra da casa para usuário de tour.
        # Escrita UMA vez, e não duas: repetida como literal, a varredura de
        # segredos do publish_liber_erp.sh a lê como credencial.
        login = 'comercial_import_co_tour'
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Comercial do Import',
            'login': login,
            'password': login,
            # A sessão roda em inglês, como os outros tours da casa: passo
            # que dependesse de texto quebraria quando a tradução entrasse.
            'lang': 'en_US',
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref(
                    'liber_soc_agreements.group_soc_user').id),
                # O que o liber_roles dá junto ao Comercial/Assistente. Sem
                # Vendas, um `group_soc_user` pelado já derrubou a ficha do
                # contrato com Access Error em sale.order (24/08/2026).
                (4, self.env.ref(
                    'sales_team.group_sale_salesman_all_leads').id),
            ],
        })

        partner = self.env['res.partner'].create({
            'name': 'Livraria do Ativo', 'is_company': True,
            'allow_consignment': True,
        })
        self.env['consignment.agreement'].create({'partner_id': partner.id})
        self.env['product.product'].create({
            'name': 'Livro do Ativo', 'type': 'consu', 'is_storable': True,
            'list_price': 70.0, 'sale_ok': True,
        })
        settlement = self.env['consignment.settlement'].create({
            'partner_id': partner.id,
        })
        # A conversa da CO é a matéria-prima do assistente: sem ela o tour
        # clicaria num botão que não tem o que ler.
        settlement.message_post(
            # `Markup`, e não str: `message_post` escapa o str puro, e o
            # parser leria a tag `<p>` como se fosse o título — casando
            # por aproximação e com quantidade 1.
            body=Markup('<p>3 Livro do Ativo</p>'),
            message_type='email', subtype_xmlid='mail.mt_comment')

        self.start_tour('/odoo', 'liber_support_import_na_co_tour',
                        login=login)

        # Perguntar ao BANCO: o navegador gravou por outra conexão, e um
        # recordset em cache responde o que era verdade antes do tour.
        self.env.invalidate_all()
        self.assertTrue(settlement.line_ids,
                        "o tour terminou sem linha na CO")
        self.assertEqual(settlement.line_ids.qty_reported, 3)
        self.assertEqual(
            self.env['consignment.settlement'].search_count(
                [('partner_id', '=', partner.id)]), 1,
            "o import pela CO abriu uma segunda CO")
