# -*- coding: utf-8 -*-
"""A camada que fala com a Amazon — sem falar com a Amazon.

Sessão de mentira em vez de rede: teste que depende da internet falha por
motivo errado e ensina a equipe a ignorar o vermelho.
"""

import ast
import inspect
import json

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..services import api as api_module
from ..services.api import AmazonVendorApi


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


class _FakeSession:
    """Registra o que foi pedido e devolve o que mandarem devolver."""

    def __init__(self, post=None, gets=None):
        self.post_response = post or _FakeResponse(
            payload={'access_token': 'Atza|fake', 'expires_in': 3600})
        self.get_responses = list(gets or [])
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.post_response

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if not self.get_responses:
            return _FakeResponse(payload={'payload': {'orders': []}})
        return self.get_responses.pop(0)


def _api(session):
    return AmazonVendorApi('id', 'secret', 'Atzr|token', 'BR', session=session)


@tagged('post_install', '-at_install', 'amazon_vendor')
class TestAmazonApi(TransactionCase):

    # ---------------------------------------------- a restrição, estrutural

    def test_module_has_no_write_path_to_amazon(self):
        """
        A promessa de "só leitura" vira teste, não comentário.

        Se alguém acrescentar um POST de acknowledgement ou um PUT de ASN
        apontado para a SP-API, esta asserção cai antes que o código chegue a
        uma base de produção. O único POST tolerado é a troca do refresh
        token, e só dentro de `_access_token` -- que fala com o servidor de
        login da Amazon, não com a API de pedidos.
        """
        tree = ast.parse(inspect.getsource(api_module))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                func = inner.func
                if not isinstance(func, ast.Attribute):
                    continue
                if func.attr in ('put', 'patch', 'delete'):
                    offenders.append('%s -> %s' % (node.name, func.attr))
                elif func.attr == 'post' and node.name != '_access_token':
                    offenders.append('%s -> post' % node.name)

        self.assertFalse(offenders, (
            "A camada da Amazon ganhou um caminho de escrita: %s. "
            "Confirmar pedido é fase 2 e não entra por aqui." % offenders))

    def test_only_the_login_server_receives_a_post(self):
        session = _FakeSession()
        _api(session).check()
        self.assertEqual(len(session.posts), 1)
        self.assertEqual(session.posts[0][0], api_module.LWA_TOKEN_URL)
        self.assertNotIn('sellingpartnerapi', session.posts[0][0])

    # ------------------------------------------------------- caminho feliz

    def test_get_carries_the_token_in_the_header(self):
        session = _FakeSession()
        _api(session).check()
        _, kwargs = session.gets[0]
        self.assertEqual(kwargs['headers']['x-amz-access-token'], 'Atza|fake')

    def test_brazil_talks_to_the_north_america_host(self):
        """Não existe host 'br'. Quem procura um perde a tarde."""
        session = _FakeSession()
        _api(session).check()
        self.assertIn('sellingpartnerapi-na.amazon.com', session.gets[0][0])

    def test_token_is_fetched_once_for_many_pages(self):
        """O LWA tem limite de taxa próprio, mais apertado que o da SP-API."""
        session = _FakeSession(gets=[
            _FakeResponse(payload={'payload': {
                'orders': [{'purchaseOrderNumber': 'A'}],
                'pagination': {'nextToken': 'tok'}}}),
            _FakeResponse(payload={'payload': {
                'orders': [{'purchaseOrderNumber': 'B'}]}}),
        ])
        orders = _api(session).purchase_orders(
            api_module.datetime(2026, 1, 1))
        self.assertEqual(len(orders), 2)
        self.assertEqual(len(session.gets), 2)
        self.assertEqual(len(session.posts), 1)

    def test_pagination_follows_next_token(self):
        session = _FakeSession(gets=[
            _FakeResponse(payload={'payload': {
                'orders': [{'purchaseOrderNumber': 'A'}],
                'pagination': {'nextToken': 'tok-2'}}}),
            _FakeResponse(payload={'payload': {
                'orders': [{'purchaseOrderNumber': 'B'}]}}),
        ])
        _api(session).purchase_orders(api_module.datetime(2026, 1, 1))
        self.assertEqual(session.gets[1][1]['params']['nextToken'], 'tok-2')

    def test_page_size_is_capped_at_the_amazon_maximum(self):
        session = _FakeSession()
        _api(session).purchase_orders(
            api_module.datetime(2026, 1, 1), page_size=500)
        self.assertEqual(session.gets[0][1]['params']['limit'], 100)

    # -------------------------------------------------------------- erros

    def test_403_explains_the_missing_role(self):
        """
        O erro mais traiçoeiro: a credencial está certa -- o LWA já respondeu
        -- e mesmo assim a chamada falha. Sem esta mensagem a pessoa passa a
        tarde conferindo o refresh token.
        """
        session = _FakeSession(gets=[_FakeResponse(403, text='Unauthorized')])
        with self.assertRaises(UserError) as caught:
            _api(session).check()
        message = str(caught.exception)
        self.assertIn('Vendor Orders', message)
        self.assertIn('Seller Central', message)

    def test_429_says_to_slow_down(self):
        session = _FakeSession(gets=[_FakeResponse(429, text='slow down')])
        with self.assertRaises(UserError) as caught:
            _api(session).check()
        self.assertIn('rate limit', str(caught.exception).lower())

    def test_rejected_refresh_token_is_readable(self):
        session = _FakeSession(
            post=_FakeResponse(400, text='{"error":"invalid_grant"}'))
        with self.assertRaises(UserError) as caught:
            _api(session).check()
        self.assertIn('400', str(caught.exception))

    def test_token_endpoint_answering_without_a_token(self):
        session = _FakeSession(post=_FakeResponse(200, payload={'ok': True}))
        with self.assertRaises(UserError):
            _api(session).check()

    def test_unknown_region_is_refused_at_construction(self):
        with self.assertRaises(UserError):
            AmazonVendorApi('id', 'secret', 'token', 'XX')

    def test_account_without_credentials_says_what_is_missing(self):
        account = self.env['liber.amazon.account'].create({
            'name': 'Half configured', 'region': 'BR',
            'client_id': 'amzn1.application-oa2-client.x',
        })
        with self.assertRaises(UserError) as caught:
            account._api()
        message = str(caught.exception)
        self.assertIn('Client Secret', message)
        self.assertIn('Refresh Token', message)
        self.assertNotIn('Client ID', message)
