# -*- coding: utf-8 -*-
"""Uma língua só: o documento tem que dizer "canal", como a ficha.

O que se testa aqui não é estética. Ficha dizendo "Canal de Vendas" e pedido
dizendo "Equipe de vendas", com os dois apontando para o MESMO `crm.team`, é
como a casa acabou com dois vocabulários para a mesma coisa -- que foi o que
levou meses de dado a divergir. O rótulo é a parte visível da unificação, e é
a que o operador lê.

Herança de view do núcleo quebra calada: se a Odoo mover o filtro de lugar num
upgrade, o `position="attributes"` some sem erro e a tela volta a falar a língua
velha. Por isso os testes leem o arch RESOLVIDO, e não o nosso arquivo.
"""
from lxml import etree

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRotuloCanal(TransactionCase):

    def test_rotulo_do_campo_no_pedido(self):
        self.assertEqual(self.env['sale.order']._fields['team_id'].string,
                         'Sales Channel')

    def test_rotulo_do_campo_na_fatura(self):
        """`account.move.team_id` vem do `sale`, não do `account`."""
        self.assertEqual(self.env['account.move']._fields['team_id'].string,
                         'Sales Channel')

    def test_o_campo_continua_sendo_o_do_nucleo(self):
        """Renomear rótulo não pode ter virado campo novo.

        Se alguém trocasse o `_inherit` por um campo próprio, os 21.660 pedidos
        e as 33.996 faturas já carimbadas ficariam órfãos -- e o pior é que a
        tela continuaria bonita.
        """
        campo = self.env['sale.order']._fields['team_id']
        self.assertEqual(campo.comodel_name, 'crm.team')
        self.assertEqual(campo.name, 'team_id')

    def _busca(self, modelo, xmlid):
        arch = self.env[modelo].get_view(
            view_id=self.env.ref(xmlid).id, view_type='search')['arch']
        return etree.fromstring(arch)

    def test_busca_do_pedido_fala_canal(self):
        arch = self._busca('sale.order', 'sale.view_sales_order_filter')
        rotulos = arch.xpath("//field[@name='team_id']/@string")
        self.assertTrue(rotulos, "o campo de equipe sumiu da busca de pedidos")
        self.assertEqual(rotulos[0], 'Sales Channel')

    def test_busca_da_fatura_fala_canal(self):
        arch = self._busca('account.move', 'account.view_account_invoice_filter')
        rotulos = arch.xpath("//filter[@name='sales_channel']/@string")
        self.assertTrue(rotulos, "o filtro `sales_channel` sumiu da busca de faturas")
        self.assertEqual(rotulos[0], 'Sales Channel')

    def test_menus_falam_canal(self):
        for xmlid in ('sale.sales_team_config', 'sale.report_sales_team'):
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if not menu:
                continue
            self.assertEqual(menu.name, 'Sales Channels', xmlid)

    def test_hook_traduz_o_menu(self):
        """O nome do menu em pt_BR não vem do `.po` -- vem do hook.

        O registro do menu é do `sale`, então o exportador nunca o atribui a
        este módulo, e nem `--i18n-overwrite` mexe em nome de menu. Se este
        teste cair, a tela volta a dizer "Equipes de vendas" só em português --
        o pior dos mundos, porque em inglês continuaria certo.
        """
        if not self.env['res.lang'].search([('code', '=', 'pt_BR'),
                                            ('active', '=', True)], limit=1):
            self.skipTest("pt_BR não está ativo neste banco")
        from odoo.addons.liber_partner_commercial.hooks import post_init_hook
        post_init_hook(self.env)
        menu = self.env.ref('sale.sales_team_config')
        self.assertEqual(menu.with_context(lang='pt_BR').name, 'Canais de Vendas')
