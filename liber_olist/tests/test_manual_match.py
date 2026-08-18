# -*- coding: utf-8 -*-
"""Casar à mão o que o ISBN não casa — e não perder esse trabalho (NOTES §13).

Dos 580 produtos do catálogo do Olist, 219 não casam por ISBN. Ao caracterizar
esses 219 (13/08/2026) o quadro foi:

    121 (55%)  o MESMO livro já existe no Odoo, com outro ISBN (reedição)
     97 (44%)  nenhum título parecido no Odoo
      1        sem código no Olist

Ou seja: criar produto para todos duplicaria metade do catálogo da editora. O
caminho é casar à mão, com sugestão por título para não fazer isso no braço —
e, sobretudo, **defender o casamento feito**: a releitura do catálogo torna a
casar por ISBN, que continua não batendo, e apagaria tudo na noite seguinte.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

CATALOGO = [
    # o ISBN do Olist é o antigo; o Odoo tem o livro com o ISBN novo
    {'id': '5001', 'codigo': '9788587329760', 'nome': 'A cena lenta – Cláudio Oliveira'},
    # este casa por ISBN, sem ajuda
    {'id': '5002', 'codigo': '9788577158355', 'nome': 'A toca iluminada'},
]


@tagged('post_install', '-at_install')
class TestOlistManualMatch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Casamento", 'company_id': cls.env.company.id,
            'token': "TOKEN-M", 'read_only': True,
        })
        # O mesmo livro, no Odoo, com o ISBN NOVO e o nome no formato da casa
        cls.reedicao = cls.env['product.product'].create({
            'name': "A cena lenta (Cláudio Oliveira. Editora Circuito)",
            'barcode': "9788595820395", 'type': 'consu'})
        cls.casa_por_isbn = cls.env['product.product'].create({
            'name': "A toca iluminada", 'barcode': "9788577158355",
            'type': 'consu'})

    def _pull(self):
        with patch.object(olist_client, 'list_produtos',
                          return_value=iter(CATALOGO)):
            self.account.action_pull_catalogue()

    def _linha(self, olist_id):
        return self.env['olist.product'].search(
            [('account_id', '=', self.account.id), ('olist_id', '=', olist_id)])

    # -- o que casa sozinho e o que não casa --------------------------------
    def test_isbn_match_is_marked_as_such(self):
        self._pull()
        linha = self._linha('5002')
        self.assertEqual(linha.product_id, self.casa_por_isbn)
        self.assertEqual(linha.match_origin, 'isbn')

    def test_reedition_does_not_match_by_isbn(self):
        self._pull()
        linha = self._linha('5001')
        self.assertFalse(linha.product_id)
        self.assertEqual(linha.state, 'sem_produto')
        self.assertFalse(linha.match_origin)

    # -- a sugestão por título ----------------------------------------------
    def test_suggestion_finds_the_book_under_another_isbn(self):
        self._pull()
        linha = self._linha('5001')
        linha.action_suggest_match()
        self.assertEqual(linha.suggested_product_id, self.reedicao,
                         "não achou o mesmo livro com o ISBN novo")
        self.assertFalse(linha.product_id, "sugestão não é casamento")

    def test_suggestion_survives_the_dash_and_the_accents(self):
        # A ordem das operações no normalizador: dobrar para ASCII antes de
        # cortar apaga o travessão (que não é ASCII) e o corte nunca acontece.
        # Foi esse engano que fez uma contagem dizer que 204 livros não
        # existiam no Odoo quando mais da metade existia.
        Mirror = self.env['olist.product']
        self.assertEqual(Mirror._titulo_chave("A cena lenta – Cláudio Oliveira"),
                         Mirror._titulo_chave(
                             "A cena lenta (Cláudio Oliveira. Editora Circuito)"))

    def test_accepting_the_suggestion_matches_by_hand(self):
        self._pull()
        linha = self._linha('5001')
        linha.action_suggest_match()
        linha.action_accept_suggestion()
        self.assertEqual(linha.product_id, self.reedicao)
        self.assertEqual(linha.match_origin, 'manual')

    # -- o que o trabalho de casar exige: não ser desfeito -------------------
    def test_manual_match_survives_a_catalogue_reload(self):
        self._pull()
        linha = self._linha('5001')
        linha.product_id = self.reedicao          # casado na mão, na lista
        self.assertEqual(linha.match_origin, 'manual')

        self._pull()                              # a releitura de amanhã
        linha.invalidate_recordset()
        self.assertEqual(linha.product_id, self.reedicao,
                         "a releitura do catálogo apagou o casamento à mão")
        self.assertEqual(linha.match_origin, 'manual')

    def test_isbn_match_is_still_refreshed_by_a_reload(self):
        # O contrário também tem de valer: o que casou por ISBN continua sendo
        # governado pelo ISBN, senão um produto trocado nunca se corrige.
        self._pull()
        linha = self._linha('5002')
        self.assertEqual(linha.match_origin, 'isbn')
        self.casa_por_isbn.barcode = "9780000000019"   # o livro mudou de código
        self._pull()
        linha.invalidate_recordset()
        self.assertFalse(linha.product_id)

    def test_unmatch_clears_the_origin_too(self):
        self._pull()
        linha = self._linha('5002')
        linha.action_unmatch()
        self.assertFalse(linha.product_id)
        self.assertFalse(linha.match_origin)

    def test_suggestion_ignores_lines_already_matched(self):
        self._pull()
        linha = self._linha('5002')
        linha.action_suggest_match()
        self.assertFalse(linha.suggested_product_id)

    # -- dois itens do Olist para um livro só do Odoo ------------------------
    def test_two_olist_items_on_one_book_are_flagged_and_not_pushed(self):
        """Aríete cinza e Aríete vinho são um livro só no Odoo.

        Mandar o saldo cheio para os dois ofereceria o mesmo exemplar duas
        vezes no marketplace — a soma no Olist ficaria com o dobro do que
        existe na prateleira.
        """
        self._pull()
        a = self._linha('5001')
        b = self._linha('5002')
        a.product_id = self.casa_por_isbn      # os dois no mesmo livro
        a.invalidate_recordset()
        b.invalidate_recordset()
        self.assertTrue(a.duplicate_match)
        self.assertTrue(b.duplicate_match)

        self.account.read_only = False
        with patch.object(olist_client, 'update_estoque') as enviou:
            acao = (a | b).action_sync_selected()
        enviou.assert_not_called()
        self.assertEqual(acao['params']['type'], 'warning')

    # -- o que vendeu: a régua para decidir o que casar ----------------------
    _seq = 0

    def _pedido_com(self, olist_id_item, codigo, qtd, situacao='Entregue'):
        # id de pedido distinto a cada chamada: dois pedidos do mesmo livro é
        # exatamente o caso que se quer somar.
        type(self)._seq += 1
        pedido = self.env['olist.order'].create({
            'account_id': self.account.id,
            'olist_id': 'P%s-%s' % (olist_id_item, self._seq),
            'numero': '%s-%s' % (olist_id_item, self._seq),
            'situacao': situacao,
            'data_pedido': '2026-01-10',
            'detalhe_lido_em': '2026-01-11 00:00:00',
        })
        pedido._sincroniza_linhas([{'item': {
            'id_produto': olist_id_item, 'codigo': codigo,
            'descricao': 'x', 'quantidade': str(qtd), 'valor_unitario': '10'}}])
        return pedido

    def test_sold_quantity_lands_on_the_catalogue_line(self):
        self._pull()
        linha = self._linha('5001')
        self._pedido_com('5001', '9788587329760', 3)
        self._pedido_com('5001', '9788587329760', 2)
        linha.invalidate_recordset()
        self.assertEqual(linha.sold_qty, 5)
        self.assertEqual(linha.sold_orders, 2)
        self.assertEqual(str(linha.last_sale_date), '2026-01-10')

    def test_sold_counts_even_without_a_matched_product(self):
        """O ponto todo: um livro que NÃO casa mostra o quanto vendeu.

        Sem isso a tela de casamento não tem régua — 219 linhas iguais, e
        ninguém sabe por onde começar.
        """
        self._pull()
        linha = self._linha('5001')
        self.assertFalse(linha.product_id)
        self._pedido_com('5001', '9788587329760', 7)
        linha.invalidate_recordset()
        self.assertEqual(linha.sold_qty, 7)

    def test_cancelled_order_is_not_a_sale(self):
        self._pull()
        linha = self._linha('5001')
        self._pedido_com('5001', '9788587329760', 4, situacao='Cancelado')
        linha.invalidate_recordset()
        self.assertEqual(linha.sold_qty, 0,
                         "pedido cancelado contou como venda")

    def test_item_finds_its_catalogue_line_by_the_isbn_too(self):
        # Sem `id_produto` no item, o código ainda encontra a linha do catálogo.
        self._pull()
        linha = self._linha('5001')
        pedido = self.env['olist.order'].create({
            'account_id': self.account.id, 'olist_id': '777',
            'numero': '777', 'situacao': 'Entregue',
            'data_pedido': '2026-02-02',
            'detalhe_lido_em': '2026-02-02 00:00:00'})
        pedido._sincroniza_linhas([{'item': {
            'codigo': '978-85-87329-76-0',   # o mesmo ISBN, com hífen
            'descricao': 'x', 'quantidade': '1', 'valor_unitario': '10'}}])
        linha.invalidate_recordset()
        self.assertEqual(linha.sold_qty, 1)
