# -*- coding: utf-8 -*-
"""A grade montada pelos campos do CATÁLOGO, e não pelo cadastro da casa.

Selo e coleção dizem de quem é o livro; não dizem PARA QUEM ele é. Feira de
escola quer infantojuvenil, lançamento quer o que saiu este ano — e as duas
perguntas se respondem no Thema e na data de publicação, que são do catálogo.
"""
from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'liber_fairs_metabooks')
class TestGradePeloCatalogo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Thema = cls.env['metabooks.thema.code']
        # O Thema é hierárquico NO PRÓPRIO CÓDIGO: Y é infantojuvenil, YF é a
        # ficção dela, YFB um ramo dela. É o que permite descer o galho por
        # prefixo, sem juntar tabela.
        cls.y = Thema.create({'code': 'Y', 'name': 'Infantojuvenil',
                              'kind': 'category'})
        cls.yfb = Thema.create({'code': 'YFB', 'name': 'Ficção infantil',
                                'kind': 'category', 'parent_code': 'YF'})
        cls.fa = Thema.create({'code': 'FA', 'name': 'Ficção adulta',
                               'kind': 'category'})

        # Uma CATEGORIA só destes quatro: o assistente varre o catálogo
        # inteiro do banco, e um teste de ordenação que olha a primeira e a
        # última linha precisa saber quais linhas existem.
        cls.categoria = cls.env['product.category'].create(
            {'name': 'Catálogo do teste de feira'})

        def livro(nome, thema=None, publicado=None):
            return cls.env['product.product'].create({
                'name': nome, 'type': 'consu', 'is_storable': True,
                'list_price': 40.0, 'categ_id': cls.categoria.id,
                'metabooks_thema_id': thema.id if thema else False,
                'metabooks_publish_date': publicado,
            })

        cls.infantil = livro('Bicho que fala', cls.yfb, date(2024, 3, 10))
        cls.juvenil = livro('Primeiro amor', cls.y, date(2026, 1, 20))
        cls.adulto = livro('Tratado do tédio', cls.fa, date(2019, 8, 1))
        cls.sem_data = livro('Sem catalogação', cls.yfb, False)

        cls.template = cls.env['event.fair.template'].create(
            {'name': 'Feira escolar', 'company_id': cls.env.company.id})

    def _assistente(self, **valores):
        # min_stock zero: modelo PLANEJA e não despacha, e o filtro de
        # estoque não é o que este teste mede.
        return self.env['event.fair.add.products'].create(dict(
            {'template_id': self.template.id, 'min_stock': 0.0,
             'filter_categ_id': self.categoria.id}, **valores))

    def test_the_thema_branch_comes_whole(self):
        """Escolher Y traz YFB junto: é o galho, não o código exato."""
        assistente = self._assistente(filter_thema_id=self.y.id)

        assistente.action_search()

        self.assertIn(self.infantil, assistente.product_ids,
                      "YFB está debaixo de Y")
        self.assertIn(self.juvenil, assistente.product_ids)
        self.assertNotIn(self.adulto, assistente.product_ids,
                         "FA não é galho de Y")

    def test_a_sibling_code_does_not_sneak_in(self):
        """Prefixo é galho, e não 'parece com'."""
        assistente = self._assistente(filter_thema_id=self.fa.id)

        assistente.action_search()

        self.assertEqual(assistente.product_ids, self.adulto)

    def test_the_publication_window(self):
        assistente = self._assistente(
            filter_published_from=date(2024, 1, 1),
            filter_published_to=date(2026, 12, 31))

        assistente.action_search()

        self.assertIn(self.infantil, assistente.product_ids)
        self.assertIn(self.juvenil, assistente.product_ids)
        self.assertNotIn(self.adulto, assistente.product_ids,
                         "2019 está fora da janela")
        self.assertNotIn(self.sem_data, assistente.product_ids,
                         "Sem data não entra numa janela de datas")

    def test_newest_first_puts_the_uncatalogued_at_the_end(self):
        """'Mais novos primeiro' com data vazia no topo mostraria justamente
        o que ninguém catalogou."""
        assistente = self._assistente(order='newest')

        assistente.action_search()

        ordenados = list(assistente.product_ids)
        self.assertEqual(ordenados[0], self.juvenil, "2026 é o mais novo")
        self.assertEqual(ordenados[-1], self.sem_data,
                         "Sem data vai para o fim, e não para o começo")
