# -*- coding: utf-8 -*-
"""Tests for the stock push to Olist (liber_olist/models/product_template.py).

No network: the Olist client is stubbed. What is worth pinning here is not the
HTTP call but the three seams that make the pilot honest -

1. the `estoque` envelope is XML keyed on the INTERNAL idProduto (not the ISBN),
   with tipo=B and a dotted decimal;
2. the raw response is always readable back, success OR error OR garbage, and
   never raises out of the reader;
3. the button resolves the idProduto from the ISBN once and remembers it, and
   keeps the raw exchange on the record.
"""
import json
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.liber_olist.models import olist_client

CLIENT = 'odoo.addons.liber_olist.models.product_template.olist_client'

OK_RESP = ('{"retorno":{"status":"OK","registros":[{"registro":'
           '{"id":9,"saldoEstoque":"42.0000","registroCriado":false}}]}}')
ERR_RESP = ('{"retorno":{"status":"Erro","codigo_erro":"6",'
            '"erros":[{"erro":"Produto nao encontrado"}]}}')


@tagged('post_install', '-at_install')
class TestOlistStockPush(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Isolate from whatever real accounts live in the dev DB: the button
        # picks an account by company with limit=1, and a real one sorting
        # ahead by name would otherwise be chosen instead of ours. Deactivating
        # is reverted with the test transaction.
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Test Olist",
            'company_id': cls.env.company.id,
            'token': "TESTTOKEN", 'read_only': False,
        })
        cls.product = cls.env['product.template'].create({
            'name': "Livro Teste",
            'barcode': "9781234567897",
            'olist_produto_id': "555",
            'type': 'consu',
            'is_storable': True,
        })

    # -- 1. the JSON envelope ------------------------------------------------
    def test_update_estoque_builds_json_on_internal_id(self):
        seen = {}

        def fake_call(token, endpoint, **params):
            seen['endpoint'] = endpoint
            seen['estoque'] = params['estoque']
            return OK_RESP

        with patch.object(olist_client, 'call', fake_call):
            req, raw = olist_client.update_estoque('T', '555', 42, tipo='B')

        self.assertEqual(seen['endpoint'], 'produto.atualizar.estoque.php')
        # JSON, not XML: under formato=json the endpoint rejects an XML envelope
        # ("ERRO JSON mal formado"). Double-wrapped like the pedido payload.
        body = json.loads(req)
        self.assertEqual(body['estoque']['idProduto'], 555)  # int, internal id
        self.assertEqual(body['estoque']['tipo'], 'B')
        self.assertEqual(body['estoque']['quantidade'], 42.0)
        self.assertNotIn('9781234567897', req)  # never the ISBN

    # -- 2. the response reader never raises ---------------------------------
    def test_read_response_ok(self):
        self.assertEqual(
            self.product._read_estoque_response(OK_RESP), ('OK', '42.0000'))

    def test_read_response_error(self):
        status, detail = self.product._read_estoque_response(ERR_RESP)
        self.assertEqual(status, 'ERR')
        self.assertEqual(detail, [{'erro': 'Produto nao encontrado'}])

    def test_read_response_garbage_does_not_raise(self):
        status, _detail = self.product._read_estoque_response('<html>429</html>')
        self.assertEqual(status, 'ERR')

    # -- 3. the button -------------------------------------------------------
    def test_push_keeps_raw_log_and_reports_success(self):
        with patch.object(olist_client, 'update_estoque',
                          return_value=('<estoque/>', OK_RESP)) as upd:
            action = self.product.action_push_stock_to_olist()

        upd.assert_called_once()
        # keyed on the stored internal id, as balanco
        self.assertEqual(upd.call_args.args[1], "555")
        self.assertEqual(upd.call_args.kwargs.get('tipo'), 'B')
        self.assertIn('RESPONSE', self.product.olist_stock_log)
        self.assertIn('42.0000', self.product.olist_stock_log)
        self.assertEqual(action['params']['type'], 'success')

    def test_push_keeps_log_even_on_error(self):
        with patch.object(olist_client, 'update_estoque',
                          return_value=('<estoque/>', ERR_RESP)):
            action = self.product.action_push_stock_to_olist()

        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('Produto nao encontrado', self.product.olist_stock_log)

    # -- 4. o envio carimba o ESPELHO ----------------------------------------
    def test_push_updates_the_mirror_line(self):
        # Pedido do dono (22/08/2026): o mesmo envio atualiza o saldo do
        # Olist no espelho — tipo=B é balanço absoluto, o número que subiu É
        # o saldo de lá. Sem isto só o botão da tela carimbava, e a
        # comparação passava semanas acusando divergência com leitura velha
        # depois de um push perfeito (os 80 "divergentes" de 22/08).
        linha = self.env['olist.product'].create({
            'account_id': self.account.id,
            'olist_id': '555',
            'codigo': self.product.barcode,
            'name': self.product.name,
        })
        with patch.object(olist_client, 'update_estoque',
                          return_value=('<estoque/>', OK_RESP)):
            self.product.action_push_stock_to_olist()
        self.assertTrue(linha.saldo_olist_date, "o envio não carimbou a data")
        self.assertTrue(linha.last_push_result.startswith('OK'),
                        "o resultado do envio não chegou ao espelho")
        self.assertEqual(linha.saldo_olist, linha.last_push_qty,
                         "saldo do espelho difere do que subiu — tipo=B "
                         "garante que os dois são o mesmo número")

    def test_a_failed_push_does_not_touch_the_mirror(self):
        # Divergência com leitura velha é ruim; divergência ESCONDIDA por um
        # carimbo de erro é pior. Erro não escreve saldo.
        linha = self.env['olist.product'].create({
            'account_id': self.account.id,
            'olist_id': '555',
            'codigo': self.product.barcode,
            'name': self.product.name,
        })
        with patch.object(olist_client, 'update_estoque',
                          return_value=('<estoque/>', ERR_RESP)):
            self.product.action_push_stock_to_olist()
        self.assertFalse(linha.saldo_olist_date,
                         "envio com erro carimbou o espelho como se certo")

    # -- 5. o casamento carimba a FICHA --------------------------------------
    def test_matching_in_the_mirror_stamps_the_product(self):
        # A varredura do cron só vê `olist_produto_id` na ficha; até
        # 22/08/2026 o casamento parava no espelho e a N1-Site ficou com
        # 217/219 livros invisíveis ao push. Casou (create ou write), a ficha
        # fica sabendo na hora — sem esperar alguém empurrar pela tela.
        livro = self.env['product.template'].create({
            'name': "Livro recém-casado", 'barcode': "9789999999991",
            'type': 'consu', 'is_storable': True})
        linha = self.env['olist.product'].create({
            'account_id': self.account.id, 'olist_id': '777',
            'codigo': livro.barcode, 'name': livro.name,
            'product_id': livro.product_variant_id.id})
        ficha = livro.with_company(self.account.company_id)
        self.assertEqual(ficha.olist_produto_id, '777',
                         "o casamento no espelho não chegou à ficha: o livro "
                         "fica invisível para a varredura do cron")
        # Carimbo existente NÃO é sobrescrito: divergência de id é notícia
        # para gente, não para um write silencioso.
        linha.write({'olist_id': '888'})
        self.assertEqual(ficha.olist_produto_id, '777')

    def test_manual_match_by_write_also_stamps(self):
        livro = self.env['product.template'].create({
            'name': "Casado à mão", 'barcode': "9789999999992",
            'type': 'consu', 'is_storable': True})
        linha = self.env['olist.product'].create({
            'account_id': self.account.id, 'olist_id': '999',
            'codigo': livro.barcode, 'name': livro.name})
        linha.write({'product_id': livro.product_variant_id.id})
        self.assertEqual(
            livro.with_company(self.account.company_id).olist_produto_id,
            '999', "o casamento à mão não carimbou a ficha")

    def test_push_resolves_and_stores_id_from_isbn(self):
        no_id = self.env['product.template'].create({
            'name': "Sem id",
            'barcode': "9780000000002",
            'type': 'consu',
            'is_storable': True,
        })
        with patch.object(olist_client, 'find_produto_id',
                          return_value="777") as finder, \
             patch.object(olist_client, 'update_estoque',
                          return_value=('<estoque/>', OK_RESP)):
            no_id.action_push_stock_to_olist()

        finder.assert_called_once_with("TESTTOKEN", "9780000000002")
        self.assertEqual(no_id.olist_produto_id, "777")

    def test_push_without_barcode_reports_error_not_raise(self):
        # A per-product problem must NOT raise (the bulk/cron loop depends on
        # it): a bare product comes back as a warning, not an exception.
        bare = self.env['product.template'].create({
            'name': "Sem ISBN",
            'type': 'consu',
        })
        action = bare.action_push_stock_to_olist()
        self.assertEqual(action['params']['type'], 'warning')

    def test_push_without_account_raises(self):
        # A configuration error (no account at all) DOES raise: it dooms every
        # push, so it must be loud.
        self.account.unlink()
        with self.assertRaises(UserError):
            self.product.action_push_stock_to_olist()

    # -- 4. bulk + cron ------------------------------------------------------
    def test_bulk_push_skips_products_not_in_olist(self):
        outside = self.env['product.template'].create({
            'name': "Fora do Olist",
            'barcode': "9780000000019",
            'type': 'consu',
            'is_storable': True,
        })
        pushed = []

        def fake_update(token, id_produto, qty, **kw):
            pushed.append(str(id_produto))
            return ('{}', OK_RESP)

        with patch.object(olist_client, 'update_estoque', side_effect=fake_update):
            res = self.account._push_all_stock(interactive=False)

        self.assertIn("555", pushed)             # our in-Olist product was sent
        self.assertGreaterEqual(res['ok'], 1)
        # the id-less product is filtered out at the search, never sent,
        # and never touched (this is the "do not create in Olist" rule).
        self.assertFalse(outside.olist_stock_log)
        self.assertTrue(self.account.last_stock_push)

    def test_cron_push_sets_timestamp(self):
        with patch.object(olist_client, 'update_estoque',
                          return_value=('{}', OK_RESP)):
            self.env['olist.account'].cron_push_stock()
        self.assertTrue(self.account.last_stock_push)


@tagged('post_install', '-at_install')
class TestPushOrcado(TransactionCase):
    """A varredura tem de caber no ciclo do cron — e retomar de onde parou.

    No prod, nas noites de 19 a 21/08/2026, o cron 58 morreu com "timed out"
    três vezes: ~580 chamadas a 2,2 s numa transação só. O Odoo derrubava tudo
    e NADA subia; na terceira falha o executor passa a pular o cron.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Push", 'company_id': cls.env.company.id,
            'token': "TOKEN-P", 'read_only': False})
        cls.livros = cls.env['product.template'].create([{
            'name': "Livro push %s" % i, 'is_storable': True,
        } for i in range(5)])
        for i, livro in enumerate(cls.livros):
            livro.with_company(cls.env.company).olist_produto_id = 'P%s' % i

    def _push(self, segundos):
        """Roda a varredura como o cron a roda, com um orçamento dado."""
        with patch.object(type(self.account), '_grava_ja',
                          return_value=segundos), \
             patch.object(olist_client, 'update_estoque',
                          return_value=True) as enviou:
            self.account._push_all_stock(interactive=False)
        return enviou

    def test_it_stops_inside_the_cycle_and_remembers_where(self):
        enviou = self._push(0.0)
        self.assertEqual(enviou.call_count, 0,
                         "começou envio que não cabia no ciclo")
        self.assertEqual(self.account.stock_push_cursor, 0)

    def test_the_next_run_resumes_instead_of_starting_over(self):
        # Uma rodada larga varre tudo e zera o cursor: a noite seguinte
        # recomeça do começo do catálogo, que é o desenho.
        enviou = self._push(9999.0)
        self.assertEqual(enviou.call_count, 5)
        self.assertEqual(self.account.stock_push_cursor, 0,
                         "varreu tudo e não voltou ao início")

    def test_a_partial_sweep_leaves_the_cursor_on_the_last_book(self):
        # `_grava_ja` devolve o orçamento ANTES de cada livro: abertura,
        # declaração da fila, e dois valores gordos — sobem dois livros e para.
        with patch.object(type(self.account), '_grava_ja',
                          side_effect=[9999.0, 9999.0, 9999.0,
                                       0.0, 0.0, 0.0, 0.0]), \
             patch.object(olist_client, 'update_estoque', return_value=True):
            self.account._push_all_stock(interactive=False)
        self.assertEqual(self.account.stock_push_cursor, self.livros[1].id,
                         "não guardou onde parou: a próxima rodada recomeça "
                         "do zero e o fim do catálogo nunca sobe")

    def test_an_empty_pass_still_declares_what_remains(self):
        # O executor dá ciclos de DEZ segundos e re-executa a ação dentro do
        # mesmo job com progresso ZERADO. Uma passada sem tempo que não
        # declara o que falta grava remaining=0 — e o executor lê "trabalho
        # concluído": foi o push de 21/08 às 21:27, três livros e dispensado
        # até o dia seguinte. A passada vazia TEM de dizer o tamanho da fila.
        with patch.object(type(self.account), '_grava_ja',
                          return_value=0.0) as grava, \
             patch.object(olist_client, 'update_estoque') as enviou:
            self.account._push_all_stock(interactive=False)
        enviou.assert_not_called()
        declarou = [c for c in grava.call_args_list
                    if c.kwargs.get('restantes') == len(self.livros)]
        self.assertTrue(
            declarou,
            "a passada vazia não declarou o que falta: o executor lê "
            "remaining=0 e dá a varredura por concluída, e o catálogo "
            "sobe a três livros por dia")

    def test_the_screen_button_is_not_budgeted(self):
        # No botão `_grava_ja` nem é chamado: quem clicou pediu a varredura.
        with patch.object(type(self.account), '_grava_ja') as orcou, \
             patch.object(olist_client, 'update_estoque', return_value=True):
            self.account._push_all_stock(interactive=True)
        orcou.assert_not_called()


@tagged('post_install', '-at_install')
class TestCloneNaoEscreve(TransactionCase):
    """Num banco neutralizado (staging/ensaio) o Olist é só-leitura, e ponto.

    A descida liga o read_only, mas trava de descida vale no momento da
    descida: um clique no toggle dias depois rearmaria a escrita na conta
    fiscal VIVA (não há token de homologação no Olist). O carimbo
    `database.is_neutralized` é quem diz "isto é clone" — e clone não
    escreve (regra do dono, 22/08/2026).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['olist.account'].search([]).write({'active': False})
        cls.account = cls.env['olist.account'].create({
            'name': "Olist Clone", 'company_id': cls.env.company.id,
            'token': "TOKEN-N", 'read_only': True})
        cls.Param = cls.env['ir.config_parameter'].sudo()

    def _neutraliza(self, valor):
        self.Param.set_param('database.is_neutralized', valor)

    def test_clone_nao_sai_do_somente_leitura(self):
        self._neutraliza('true')
        with self.assertRaises(UserError):
            self.account.read_only = False
        self.assertTrue(self.account.read_only)

    def test_conta_nova_no_clone_nasce_lendo(self):
        self._neutraliza('true')
        self.account.active = False     # uma conta ativa por empresa
        conta = self.env['olist.account'].create({
            'name': "Nova no clone", 'company_id': self.env.company.id,
            'token': "TOKEN-N2", 'read_only': False})
        self.assertTrue(conta.read_only,
                        "conta criada num clone nasceu escrevendo")

    def test_no_prod_o_toggle_continua_livre(self):
        # Caso de controle: fora do clone a decisão segue sendo de gente.
        self._neutraliza('false')
        self.account.read_only = False
        self.assertFalse(self.account.read_only)
