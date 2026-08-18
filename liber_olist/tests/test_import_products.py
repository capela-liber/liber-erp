# -*- coding: utf-8 -*-
"""O espelho do catálogo não inventa produto (liber_olist/NOTES.md §10.8).

`action_import_products` nasceu num banco de ensaio VAZIO, onde criar produto a
partir do Olist era o jeito de ter o que testar. Numa base com catálogo de
verdade isso se inverte: o Odoo é o razão, o Olist é o adaptador, e um ISBN que
não casa é notícia — dígito errado, livro de outro selo, produto arquivado —,
não motivo para nascer um livro duplicado no catálogo da editora.

Daí o padrão ser NÃO criar, e a criação ser uma escolha explícita por conta.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

# Um casa por ISBN, o outro não existe no Odoo.
CATALOGO = [
    {'id': '321', 'codigo': '9787777777771', 'nome': "Livro Conhecido",
     'preco': '50.00'},
    {'id': '654', 'codigo': '9786666666664', 'nome': "Livro Desconhecido",
     'preco': '60.00'},
]


@tagged('post_install', '-at_install')
class TestOlistImportProducts(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Catálogo", 'company_id': cls.env.company.id,
            'token': "TOKEN-C", 'read_only': False,
        })
        cls.conhecido = cls.env['product.product'].create({
            'name': "Livro Conhecido (nome nosso)",
            'barcode': '9787777777771',
            'list_price': 99.0,
            'type': 'consu',
        })

    def _run(self):
        with patch.object(olist_client, 'list_produtos',
                          return_value=iter(CATALOGO)):
            return self.account.action_import_products()

    def test_default_never_creates(self):
        antes = self.env['product.product'].search_count([])
        res = self._run()
        self.assertEqual(res['created'], 0)
        self.assertEqual(res['matched'], 1)
        self.assertEqual(res['missing'], 1, "o ISBN sem par tem de ser contado")
        self.assertEqual(self.env['product.product'].search_count([]), antes,
                         "nasceu produto no catálogo da editora")

    def test_match_stores_the_internal_id_and_leaves_the_rest_alone(self):
        self._run()
        self.assertEqual(
            self.conhecido.product_tmpl_id.olist_produto_id, "321")
        # nome e preço são nossos: o Olist não os reescreve
        self.assertEqual(self.conhecido.name, "Livro Conhecido (nome nosso)")
        self.assertEqual(self.conhecido.list_price, 99.0)

    def test_unmatched_isbn_gets_no_id_anywhere(self):
        self._run()
        self.assertFalse(self.env['product.product'].search(
            [('barcode', '=', '9786666666664')]))

    def test_creating_is_possible_but_deliberate(self):
        self.account.create_missing_products = True
        res = self._run()
        self.assertEqual(res['created'], 1)
        novo = self.env['product.product'].search(
            [('barcode', '=', '9786666666664')])
        self.assertTrue(novo)
        self.assertEqual(novo.product_tmpl_id.olist_produto_id, "654")

    def test_the_stored_id_is_per_company(self):
        # O id casado entra na empresa da CONTA, não na de quem apertou o botão.
        outra = self.env['res.company'].search(
            [('id', '!=', self.account.company_id.id)], limit=1)
        if not outra:
            self.skipTest("banco com uma empresa só")
        self._run()
        tmpl = self.conhecido.product_tmpl_id
        self.assertEqual(
            tmpl.with_context(
                allowed_company_ids=[self.account.company_id.id]
            ).olist_produto_id, "321")
        self.assertFalse(
            tmpl.with_context(allowed_company_ids=[outra.id]).olist_produto_id)
