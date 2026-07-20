# -*- coding: utf-8 -*-
"""Pure HTTP client for the Metabooks (MVB) API.

No Odoo dependency here on purpose: this is plain `requests` code so it can be
unit-tested and reasoned about in isolation. The Odoo layer (metabooks.connector)
builds an instance from ir.config_parameter and persists the token via `on_token`.

API contract (v2):
  * POST /login              {username, password} -> body is the raw bearer token
  * GET  /product/{isbn}/isbn13                    -> full ONIX product
  * GET  /products?search=VL=<mvbId>&page=N        -> paginated publisher catalog
"""
import logging

import requests

_logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://www.metabooks.com/api/v2"


class MetabooksError(Exception):
    """Any Metabooks API failure (network, auth, HTTP status)."""


def clean_isbn(isbn):
    """Normalise an ISBN/GTIN to digits only (the API wants no separators)."""
    if not isbn:
        return ""
    return "".join(ch for ch in str(isbn) if ch.isdigit() or ch in ("X", "x")).upper()


class MetabooksClient:
    def __init__(self, username, password, base_url=DEFAULT_BASE_URL,
                 token=None, timeout=30, on_token=None):
        self.username = username
        self.password = password
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.token = token
        self.timeout = timeout
        # optional callback(token: str) used to persist a freshly obtained token
        self.on_token = on_token

    # -- auth -------------------------------------------------------------
    def login(self):
        url = "%s/login" % self.base_url
        try:
            resp = requests.post(
                url,
                json={"username": self.username, "password": self.password},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise MetabooksError("Could not reach Metabooks (%s): %s" % (url, exc))
        if resp.status_code != 200:
            raise MetabooksError(
                "Metabooks login failed (HTTP %s). Check username/password."
                % resp.status_code
            )
        self.token = (resp.text or "").strip()
        if not self.token:
            raise MetabooksError("Metabooks login returned an empty token.")
        if self.on_token:
            self.on_token(self.token)
        return self.token

    def _headers(self):
        if not self.token:
            self.login()
        return {
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % self.token,
        }

    # -- low-level GET with one automatic re-login on 401 -----------------
    def _get(self, path, params=None):
        url = "%s/%s" % (self.base_url, path.lstrip("/"))
        try:
            resp = requests.get(url, headers=self._headers(), params=params,
                                 timeout=self.timeout)
            if resp.status_code == 401:
                # token expired: log in again and retry once
                self.login()
                resp = requests.get(url, headers=self._headers(), params=params,
                                    timeout=self.timeout)
        except requests.RequestException as exc:
            raise MetabooksError("Metabooks request failed (%s): %s" % (url, exc))
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise MetabooksError("Metabooks returned HTTP %s for %s"
                                 % (resp.status_code, url))
        try:
            return resp.json()
        except ValueError:
            raise MetabooksError("Metabooks returned a non-JSON response for %s" % url)

    # -- public API -------------------------------------------------------
    def test_connection(self):
        """Raise MetabooksError if credentials/host are invalid, else True."""
        self.login()
        return True

    def get_product_by_isbn(self, isbn):
        """Full ONIX product for one ISBN, or None if not found."""
        return self._get("product/%s/isbn13" % clean_isbn(isbn))

    def catalog_page(self, mvb_id, page):
        """One page of a publisher (VL) catalogue: {totalPages, totalElements, content}."""
        return self._get("products", params={"search": "VL=%s" % mvb_id, "page": page})

    def publisher_count(self, mvb_id):
        """Number of products in a publisher (VL) catalogue."""
        data = self.catalog_page(mvb_id, 1)
        return (data or {}).get("totalElements", 0)

    def iter_publisher_products(self, mvb_id, limit=None):
        """Yield each catalogue feed item for a publisher, across all pages.

        Feed items are already denormalised (isbn, title, author, coverUrl,
        priceBrl, collections, ...), so a whole catalogue costs ~totalPages
        calls rather than one call per ISBN.
        """
        first = self.catalog_page(mvb_id, 1)
        if not first:
            return
        total_pages = first.get("totalPages", 1) or 1
        count = 0
        for page in range(1, total_pages + 1):
            data = first if page == 1 else self.catalog_page(mvb_id, page)
            for item in (data or {}).get("content", []):
                yield item
                count += 1
                if limit and count >= limit:
                    return
