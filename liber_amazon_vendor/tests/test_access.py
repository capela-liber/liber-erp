# -*- coding: utf-8 -*-
"""Quem pode o quê. O refresh token é a conta inteira — ele não circula."""

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import AmazonVendorCase, amazon_item, amazon_order


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonAccess(AmazonVendorCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = cls.env['res.users'].create({
            'name': 'Operadora Amazon',
            'login': 'amazon_operator',
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('liber_amazon_vendor.group_liber_amazon_user').id,
            ])],
        })
        cls.outsider = cls.env['res.users'].create({
            'name': 'Alguém de outra área',
            'login': 'amazon_outsider',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def test_operator_reads_orders(self):
        self._sync([amazon_order('BR-2000', [amazon_item('1', '9786551590016')])])
        order = self._order('BR-2000').with_user(self.operator)
        self.assertEqual(order.name, 'BR-2000')

    def test_operator_cannot_read_the_refresh_token(self):
        """
        Com o refresh token se obtém access token para tudo que o app
        autoriza. Quem importa pedido não precisa dele, e o que não é preciso
        não se entrega.
        """
        account = self.account.with_user(self.operator)
        with self.assertRaises(AccessError):
            account.refresh_token  # noqa: B018 - a leitura é o teste

    def test_operator_can_fix_the_product_of_a_line(self):
        """Corrigir o casamento é justamente o trabalho do operador."""
        self._sync([amazon_order('BR-2001', [amazon_item('1', '9788500000009')])])
        line = self._order('BR-2001').line_ids.with_user(self.operator)
        line.product_id = self.book_a
        self.assertEqual(line.product_id, self.book_a)

    def test_operator_cannot_change_the_account(self):
        with self.assertRaises(AccessError):
            self.account.with_user(self.operator).write({'name': 'Outro nome'})

    def test_outsider_sees_nothing(self):
        self._sync([amazon_order('BR-2002', [amazon_item('1', '9786551590016')])])
        with self.assertRaises(AccessError):
            self._order('BR-2002').with_user(self.outsider).read(['name'])

    def test_admin_gets_the_app_on_install(self):
        """
        Um módulo cujos menus exigem grupo, e cujo grupo não tem ninguém,
        instala e some: o app não aparece na lista e não há erro nenhum para
        explicar por quê. Foi exatamente o que aconteceu na primeira
        instalação real.
        """
        admin = self.env.ref('base.user_admin')
        self.assertTrue(admin.has_group(
            'liber_amazon_vendor.group_liber_amazon_manager'))
        self.assertTrue(admin.has_group(
            'liber_amazon_vendor.group_liber_amazon_user'))

    def test_operator_is_a_salesperson(self):
        """
        Sem isto o operador importa tudo e trava no único botão que importa,
        com um erro de permissão que não explica nada.
        """
        self.assertTrue(self.operator.has_group('sales_team.group_sale_salesman'))
