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
