# -*- coding: utf-8 -*-
"""O espelho do Olist e a tela de conferência (liber_olist/NOTES.md §11).

O que se prova aqui não é a API — é o que a pessoa vê e decide:

* o espelho guarda o que o Olist DIZ, com a data em que foi lido, separado do
  que o Odoo sabe. Só assim existe "divergência" para ordenar e filtrar;
* a conta nasce em SOMENTE LEITURA, e enquanto estiver nada é escrito no
  Olist. É o que deixa instalar no `dev` — cópia do prod — com o token de
  verdade, já que o Olist não tem ambiente de homologação;
* sincronizar é ação sobre linhas ESCOLHIDAS, não sobre o catálogo;
* linha sem produto no Odoo nunca é enviada.
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

OK_RESP = ('{"retorno":{"status":"OK","registros":[{"registro":'
           '{"id":9,"saldoEstoque":"8.0000","registroCriado":false}}]}}')

CATALOGO = [
    {'id': '111', 'codigo': '9781111111119', 'nome': "Livro Casado",
     'situacao': 'A'},
    {'id': '222', 'codigo': '9782222222226', 'nome': "Livro Sem Par",
     'situacao': 'A'},
]


@tagged('post_install', '-at_install')
class TestOlistMirror(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1)
        cls.company = cls.warehouse.company_id
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Espelho", 'company_id': cls.company.id,
            'token': "TOKEN-E",
        })
        cls.livro = cls.env['product.product'].create({
            'name': "Livro Casado (nosso nome)",
            'barcode': '9781111111119',
            'type': 'consu', 'is_storable': True,
        })
        cls.env['stock.quant'].sudo()._update_available_quantity(
            cls.livro, cls.warehouse.lot_stock_id, 8.0)

    def _pull(self):
        with patch.object(olist_client, 'list_produtos',
                          return_value=iter(CATALOGO)):
            return self.account.action_pull_catalogue()

    # -- o espelho -----------------------------------------------------------
    def test_pull_creates_the_mirror_and_matches_by_isbn(self):
        self._pull()
        linhas = self.env['olist.product'].search(
            [('account_id', '=', self.account.id)])
        self.assertEqual(len(linhas), 2)
        casada = linhas.filtered(lambda l: l.olist_id == '111')
        orfa = linhas.filtered(lambda l: l.olist_id == '222')
        self.assertEqual(casada.product_id, self.livro)
        self.assertFalse(orfa.product_id)
        self.assertEqual(orfa.state, 'sem_produto')

    def test_pull_twice_updates_instead_of_duplicating(self):
        self._pull()
        self._pull()
        self.assertEqual(self.env['olist.product'].search_count(
            [('account_id', '=', self.account.id)]), 2)

    def test_comparison_is_olist_minus_what_we_would_send(self):
        self._pull()
        linha = self.env['olist.product'].search(
            [('account_id', '=', self.account.id), ('olist_id', '=', '111')])
        linha.saldo_olist = 20.0
        self.assertEqual(linha.odoo_qty, 8.0)
        self.assertEqual(linha.qty_to_send, 8.0)
        self.assertEqual(linha.divergencia, 12.0)
        self.assertEqual(linha.state, 'olist_maior')

        self.account.stock_reserve = 3
        linha.invalidate_recordset()
        self.assertEqual(linha.qty_to_send, 5.0, "a margem entra na comparação")
        self.assertEqual(linha.divergencia, 15.0)

    def test_equal_when_olist_already_has_our_number(self):
        self._pull()
        linha = self.env['olist.product'].search(
            [('account_id', '=', self.account.id), ('olist_id', '=', '111')])
        linha.saldo_olist = 8.0
        self.assertEqual(linha.state, 'igual')
        self.assertEqual(linha.divergencia, 0.0)

    # -- a trava de somente leitura -----------------------------------------
    def test_account_is_read_only_when_created(self):
        self.assertTrue(self.account.read_only,
                        "uma conta nova não pode nascer podendo escrever")

    def test_sync_refuses_while_read_only(self):
        self._pull()
        linha = self.env['olist.product'].search(
            [('account_id', '=', self.account.id), ('olist_id', '=', '111')])
        with patch.object(olist_client, 'update_estoque') as escrita:
            with self.assertRaises(UserError):
                linha.action_sync_selected()
        escrita.assert_not_called()

    def test_push_paths_all_refuse_while_read_only(self):
        # A trava tem de estar no caminho por onde TODA escrita passa, não só
        # na tela nova: o botão do produto e a varredura da conta também.
        with patch.object(olist_client, 'update_estoque') as escrita:
            with self.assertRaises(UserError):
                self.livro.product_tmpl_id._push_stock_to_olist(self.account)
            with self.assertRaises(UserError):
                self.account._push_all_stock(interactive=False)
        escrita.assert_not_called()

    def test_reading_works_while_read_only(self):
        # O ponto do modo: dá para conferir tudo sem poder estragar nada.
        self._pull()
        with patch.object(olist_client, 'get_estoque',
                          return_value={'saldo': '20'}):
            self.env['olist.product'].search(
                [('account_id', '=', self.account.id)]).action_read_saldo()
        linha = self.env['olist.product'].search(
            [('account_id', '=', self.account.id), ('olist_id', '=', '111')])
        self.assertEqual(linha.saldo_olist, 20.0)
        self.assertTrue(linha.saldo_olist_date)

    # -- sincronizar selecionados -------------------------------------------
    def test_sync_selected_sends_only_the_chosen_lines(self):
        self.account.read_only = False
        self._pull()
        linhas = self.env['olist.product'].search(
            [('account_id', '=', self.account.id)])
        casada = linhas.filtered(lambda l: l.olist_id == '111')
        casada.saldo_olist = 99.0

        enviados = []

        def fake_update(token, id_produto, qty, **kw):
            enviados.append((str(id_produto), qty))
            return ('{}', OK_RESP)

        with patch.object(olist_client, 'update_estoque',
                          side_effect=fake_update), \
             patch.object(olist_client, 'find_produto_id') as procura:
            casada.action_sync_selected()

        self.assertEqual(len(enviados), 1, "só a linha escolhida foi enviada")
        self.assertEqual(enviados[0][0], '111', "usou o id que o espelho já tinha")
        self.assertEqual(enviados[0][1], 8.0)
        # O espelho conhece o id interno: procurar o produto por ISBN seria
        # uma ida à rede por livro para descobrir o que já está aqui.
        procura.assert_not_called()
        # o espelho reflete o que acabou de ser escrito, sem outra chamada
        self.assertEqual(casada.saldo_olist, 8.0)
        self.assertEqual(casada.state, 'igual')
        self.assertTrue(casada.last_push_date)

    def test_sync_never_sends_a_line_without_product(self):
        self.account.read_only = False
        self._pull()
        orfa = self.env['olist.product'].search(
            [('account_id', '=', self.account.id), ('olist_id', '=', '222')])
        with patch.object(olist_client, 'update_estoque') as escrita:
            orfa.action_sync_selected()
        escrita.assert_not_called()

    # -- a janela do cron ----------------------------------------------------
    def test_window_updates_only_what_changed(self):
        self._pull()
        with patch.object(olist_client, 'list_atualizacoes_estoque',
                          return_value=[{'id': '111', 'saldo': '42'}]) as janela:
            self.account._pull_stock_window()
        janela.assert_called_once()
        linha = self.env['olist.product'].search(
            [('account_id', '=', self.account.id), ('olist_id', '=', '111')])
        self.assertEqual(linha.saldo_olist, 42.0)
        self.assertTrue(self.account.last_stock_pull)

    def test_window_never_writes_to_olist(self):
        self._pull()
        self.account.read_only = False  # mesmo liberada, a janela só lê
        with patch.object(olist_client, 'list_atualizacoes_estoque',
                          return_value=[]), \
             patch.object(olist_client, 'update_estoque') as escrita:
            self.env['olist.account'].cron_pull_stock_window()
        escrita.assert_not_called()
