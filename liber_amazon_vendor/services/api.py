# -*- coding: utf-8 -*-
"""
A porta para a Amazon -- e ela só abre para dentro.

Este módulo LÊ a Vendor Central e mais nada. Não confirma pedido, não manda
ASN, não emite invoice, não cancela linha. Isso não é omissão a ser corrigida
depois: é o contrato do módulo. Confirmar um pedido na Amazon dispara relógio
de SLA e compromisso de entrega, e essa decisão pertence a uma pessoa, não a
um cron.

A regra é estrutural, não uma promessa no comentário: a única função que faz
POST aqui é `_access_token`, e ela fala com `api.amazon.com` -- o servidor de
autenticação da Amazon, que não conhece pedido nenhum. Todo acesso ao host da
SP-API passa por `_get`, que só sabe fazer GET. Há um teste que lê este
arquivo e falha se alguém acrescentar um verbo de escrita apontado para a
SP-API.

Não usa `python-amazon-sp-api`. Desde 2023 a SP-API não exige mais assinatura
AWS SigV4 nem role IAM: o access token do LWA no header `x-amz-access-token`
é a credencial inteira. `requests` basta, e o Odoo já o tem -- nenhuma
dependência nova, nenhum Dockerfile alterado.
"""

import logging
from datetime import datetime, timedelta, timezone

import requests

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

# O Brasil é atendido pelo endpoint da América do Norte. Surpreende quem
# procura um host "br"; ele não existe.
REGION_HOSTS = {
    "BR": "sellingpartnerapi-na.amazon.com",
    "US": "sellingpartnerapi-na.amazon.com",
    "CA": "sellingpartnerapi-na.amazon.com",
    "MX": "sellingpartnerapi-na.amazon.com",
    "UK": "sellingpartnerapi-eu.amazon.com",
    "DE": "sellingpartnerapi-eu.amazon.com",
    "FR": "sellingpartnerapi-eu.amazon.com",
    "IT": "sellingpartnerapi-eu.amazon.com",
    "ES": "sellingpartnerapi-eu.amazon.com",
    "JP": "sellingpartnerapi-fe.amazon.com",
    "AU": "sellingpartnerapi-fe.amazon.com",
}

PURCHASE_ORDERS_PATH = "/vendor/orders/v1/purchaseOrders"

# A Amazon devolve no máximo 100 pedidos por página.
MAX_PAGE_SIZE = 100

# Trava contra paginação que não termina. 200 páginas são 20.000 pedidos: mais
# do que qualquer janela sensata de importação, e menos do que um laço infinito
# segurando um worker do Odoo.
MAX_PAGES = 200


class AmazonVendorApi:
    """Cliente somente-leitura da Vendor Orders API."""

    def __init__(self, client_id, client_secret, refresh_token, region,
                 timeout=60, session=None):
        if region not in REGION_HOSTS:
            raise UserError(_(
                "Unknown Amazon region %(region)s. Known regions: %(known)s",
                region=region, known=", ".join(sorted(REGION_HOSTS))))
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.region = region
        self.host = REGION_HOSTS[region]
        self.timeout = timeout
        self.session = session or requests
        self._token = None
        self._token_expires = None

    # ------------------------------------------------------------ autenticação

    def _access_token(self):
        """
        Troca o refresh token por um access token, e o guarda.

        O access token vale uma hora. Renovar a cada chamada funcionaria, mas
        gastaria uma ida ao LWA por página de pedidos -- e o LWA tem limite de
        taxa próprio, mais apertado que o da SP-API. Guardamos com um minuto
        de folga para não usar um token que expira no voo.
        """
        now = datetime.now(timezone.utc)
        if self._token and self._token_expires and now < self._token_expires:
            return self._token

        try:
            response = self.session.post(
                LWA_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise UserError(_(
                "Could not reach Amazon's login server: %s", exc)) from exc

        if response.status_code != 200:
            raise UserError(_(
                "Amazon refused these credentials (HTTP %(code)s).\n\n%(body)s",
                code=response.status_code, body=response.text[:400]))

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise UserError(_("Amazon replied 200 but sent no access token."))

        self._token = token
        expires_in = int(payload.get("expires_in") or 3600)
        self._token_expires = now + timedelta(seconds=max(expires_in - 60, 60))
        return token

    # -------------------------------------------------------------- leitura

    def _get(self, path, params):
        """
        O único caminho até a SP-API. Faz GET e nada mais.

        Traduz os erros que a pessoa vai realmente encontrar. O 403 é o mais
        traiçoeiro: as credenciais estão certas -- o LWA já respondeu -- e
        mesmo assim a chamada falha, porque falta o papel de Vendor Orders no
        app do Developer Central, ou porque a autorização foi feita para
        Seller Central em vez de Vendor. Sem essa mensagem a pessoa passa a
        tarde conferindo o refresh token.
        """
        url = "https://%s%s" % (self.host, path)
        try:
            response = self.session.get(
                url,
                headers={
                    "x-amz-access-token": self._access_token(),
                    "Accept": "application/json",
                },
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise UserError(_("Could not reach Amazon: %s", exc)) from exc

        if response.status_code == 403:
            raise UserError(_(
                "Amazon accepted the credentials but refused the Vendor "
                "Orders API (HTTP 403).\n\nThis is usually not a wrong "
                "password: check that the app has the Vendor Orders role in "
                "Developer Central, and that the authorisation was granted "
                "for Vendor Central and not Seller Central.\n\n%s",
                response.text[:400]))
        if response.status_code == 429:
            raise UserError(_(
                "Amazon is rate limiting us (HTTP 429). Try a shorter date "
                "range, or run the import again in a few minutes."))
        if response.status_code != 200:
            raise UserError(_(
                "Amazon refused the request (HTTP %(code)s).\n\n%(body)s",
                code=response.status_code, body=response.text[:400]))

        return response.json().get("payload") or {}

    def check(self):
        """
        Prova que a conta fala com a Amazon, sem importar nada.

        Pede uma janela de um dia e uma página de tamanho 1: o objetivo é
        provocar a resposta, não colher dados.
        """
        since = datetime.now(timezone.utc) - timedelta(days=1)
        payload = self._get(PURCHASE_ORDERS_PATH, {
            "createdAfter": iso_utc(since),
            "limit": 1,
            "includeDetails": "false",
        })
        return {"region": self.region, "host": self.host,
                "orders_last_day": len(payload.get("orders") or [])}

    def purchase_orders(self, created_after, created_before=None,
                        page_size=MAX_PAGE_SIZE):
        """
        Devolve os purchase orders da janela, virando as páginas sozinho.

        `created_after` e `created_before` são datetime. A Vendor API não
        recebe `marketplaceIds`: o token já diz de qual vendor se trata, e o
        que muda por país é só o host.
        """
        params = {
            "createdAfter": iso_utc(created_after),
            "limit": min(int(page_size), MAX_PAGE_SIZE),
            "includeDetails": "true",
        }
        if created_before:
            params["createdBefore"] = iso_utc(created_before)

        orders = []
        next_token = None
        for page in range(MAX_PAGES):
            if next_token:
                params["nextToken"] = next_token
            payload = self._get(PURCHASE_ORDERS_PATH, params)
            batch = payload.get("orders") or []
            if not batch:
                break
            orders.extend(batch)
            next_token = (payload.get("pagination") or {}).get("nextToken")
            if not next_token:
                break
            _logger.info("Amazon Vendor: page %s read, %s orders so far",
                         page + 1, len(orders))
        else:
            _logger.warning(
                "Amazon Vendor: stopped at %s pages. Narrow the date range.",
                MAX_PAGES)

        return orders


def iso_utc(value):
    """Formata datetime no ISO 8601 com Z que a SP-API espera.

    Datetime ingênuo -- que é como o Odoo guarda tudo -- é lido como UTC, que
    é como o Odoo guarda tudo.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
