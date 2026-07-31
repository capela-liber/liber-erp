# -*- coding: utf-8 -*-
"""One door for every Metabrasil HTTP call.

The O15 connector sprinkled requests.* calls (all of them without a timeout)
across four files; a slow API froze crons and workers alike. Here every call
goes through _request(): hard timeout, basic auth from the company, JSON in
and out, and a contract that never raises for the caller -- transport
failures come back as (None, {'error': ...}) so a cron sweeping fifty orders
survives the one that hangs.
"""
import json
import logging

import requests
from requests.auth import HTTPBasicAuth

from odoo import _, api, models

_logger = logging.getLogger(__name__)

TIMEOUT = 30  # seconds; the printer's API is slow but not THAT slow


class MetabrasilApi(models.AbstractModel):
    _name = 'metabrasil.api'
    _description = 'Metabrasil PoD API Client'

    @api.model
    def _request(self, company, method, path, payload=None):
        """Perform one API call for `company`.

        Returns (status_code, data):
        * (200, {...})    -- parsed JSON on success;
        * (4xx/5xx, {...}) -- parsed body (or {'error': raw text}) on HTTP error;
        * (None, {'error': msg}) -- transport failure (DNS, refused, timeout);
        * (0, {}) -- Metabrasil is not configured/enabled for this company.
        Callers decide what each of these means; nothing is raised.
        """
        url = company._get_metabrasil_url()
        if not url:
            return 0, {}
        auth = HTTPBasicAuth(company.metabrasil_username or '',
                             company.metabrasil_password or '')
        try:
            response = requests.request(
                method, url.rstrip('/') + path,
                headers={'Content-Type': 'application/json'},
                auth=auth, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            _logger.warning("Metabrasil %s %s failed: %s", method, path, exc)
            return None, {'error': str(exc)}
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError):
            data = {'error': (response.text or '')[:2000]}
        if response.status_code != 200:
            _logger.info("Metabrasil %s %s -> %s %s",
                         method, path, response.status_code, data)
        return response.status_code, data

    @api.model
    def error_text(self, data):
        """The human-readable reason out of a Metabrasil error body.

        Their errors are structured JSON that varies by layer: a validation
        rejection carries `titulo` ("O bairro_entrega não foi informado"), a
        Spring fault carries `error`/`message`, our transport failures carry
        `error`. Rendering the raw dict showed only its keys; this digs out
        the sentence a person can act on.
        """
        if not isinstance(data, dict):
            return str(data)
        return (data.get('titulo') or data.get('error') or data.get('message')
                or data.get('exception') or str(data))

    # ------------------------------------------------------------------
    # The four calls the module makes
    # ------------------------------------------------------------------
    @api.model
    def post_order(self, company, payload):
        """POST /pedidos -- send a print order."""
        return self._request(company, 'POST', '/pedidos', payload)

    @api.model
    def get_order(self, company, order_code):
        """GET /pedidos -- status of one order.

        Their contract wants the JSON in the GET body (unusual, but that is
        the API we have; proxies between us and them have coped so far).
        """
        return self._request(company, 'GET', '/pedidos', {
            'chaveCliente': company.metabrasil_access_key,
            'codigoEncomenda': order_code,
        })

    @api.model
    def freight_rates(self, company, cep, items):
        """POST /fretes/{cep}/rates/isbn -- carriers with price and days."""
        cep = ''.join(ch for ch in (cep or '') if ch.isdigit())
        if not cep:
            return None, {'error': 'no destination CEP'}
        return self._request(company, 'POST', '/fretes/%s/rates/isbn' % cep, {
            'chaveCliente': company.metabrasil_access_key,
            'listaItems': items,
        })

    @api.model
    def test_connection(self, company):
        """Read-only probe of the current mode's endpoint.

        Rides the freight quote (`/fretes`) -- the manifest's designated safe
        read -- so a "Test Connection" click can never post a print order. It
        classifies the outcome so Settings can say *which* knob is wrong:

        * cannot reach the host (DNS/refused/timeout) -> the URL is wrong or
          the printer is down;
        * reached but 401/403 -> the host is fine, the credentials are not;
        * 200 -> everything answers;
        * any other HTTP status -> connection and auth cleared, the printer's
          app just rejected the probe payload (for a live key this usually
          means only that the throwaway test ISBN is unknown -- still proof
          the pipe is open).

        Returns {'level': success|warning|danger, 'message': str} ready for a
        display_notification.
        """
        if not company._get_metabrasil_url():
            return {'level': 'warning',
                    'message': _("Metabrasil is off, or the %s mode has no "
                                 "API URL set.") % (company.metabrasil_mode or '')}
        # A throwaway CEP (Av. Paulista) and one probe item in the SHAPE the
        # printer's app dereferences -- preco/quantidade/referenciaISBN. Wrong
        # keys make their Spring app NPE (HTTP 500), which looks like a server
        # fault but is really a malformed body; the ISBN is a real one from
        # Metabrasil's own API sample, to stand the best chance of a clean 200.
        status, data = self.freight_rates(company, '01310100', [{
            'preco': 1.0,
            'quantidade': 1,
            'referenciaISBN': '9788555931888',
        }])
        url = company._get_metabrasil_url()
        if status is None:
            return {'level': 'danger',
                    'message': _("Could not reach %(url)s: %(err)s",
                                 url=url, err=data.get('error', ''))}
        if status in (401, 403):
            return {'level': 'danger',
                    'message': _("Reached %(url)s but it refused the "
                                 "credentials (HTTP %(code)s). Check the "
                                 "access key and the API user/password.",
                                 url=url, code=status)}
        if status == 200:
            return {'level': 'success',
                    'message': _("Connection OK — %s answered.") % url}
        return {'level': 'warning',
                'message': _("Reached %(url)s (HTTP %(code)s). The connection "
                             "opened and the credentials were not refused, but "
                             "Metabrasil's app returned an error for the probe "
                             "request. Try again; if it persists, the endpoint "
                             "itself is unwell.", url=url, code=status)}

    @api.model
    def production_prices(self, company, isbn, tiragens):
        """POST /pod-api/precificacao -- production cost per print run.

        Draft endpoint being negotiated with Metabrasil (2026-07): `valor` is
        the PRODUCTION cost only; freight stays with freight_rates(). Callers
        must degrade gracefully while it does not exist on their side.

        Path is '/precificacao', NOT '/pod-api/precificacao': the company base
        URL already ends in '/pod-api' (the spec writes the full path as
        POST /pod-api/precificacao), so prefixing it again doubled it into
        /pod-api/pod-api/precificacao and always 404'd.
        """
        return self._request(company, 'POST', '/precificacao', {
            'chave': company.metabrasil_access_key,
            'isbn': isbn,
            'tiragens': tiragens,
        })
