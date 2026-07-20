# -*- coding: utf-8 -*-
import base64
import json
import logging
import re

from odoo import http
from odoo.http import request
from odoo.tools import file_open

from ..analysis import pipeline

_logger = logging.getLogger(__name__)

# Rendered panel cache, one entry per (database, active companies). The
# payload takes a few seconds to build from thousands of XMLs, so reuse it
# until the visible record set changes: (record count, latest write_date).
_CACHE = {}


class NfeXmlPainel(http.Controller):

    @http.route('/liber_nfe_xml/painel', type='http', auth='user')
    def painel(self, **kw):
        self._apply_company_switcher()
        env = request.env
        panels = env['nfe.xml.panel'].search([('status', '!=', 'cancelled')])
        companies = tuple(env.companies.ids)
        sig = (env.uid, companies, len(panels),
               max(panels.mapped('write_date'), default=None))
        key = (env.cr.dbname, companies)
        cached = _CACHE.get(key)
        if cached and cached[0] == sig:
            html = cached[1]
        else:
            html = self._render(env, panels)
            _CACHE[key] = (sig, html)
        return request.make_response(html, [('Content-Type', 'text/html; charset=utf-8')])

    @staticmethod
    def _apply_company_switcher():
        """Honor the web client's company switcher on this plain HTTP route.

        The switcher only travels in RPC contexts, not in a bare page load;
        what does reach us is the `cids` cookie. Without this, env.companies
        falls back to every company the user can access and the panel always
        shows everything.
        """
        cids = request.httprequest.cookies.get('cids')
        if not cids:
            return
        try:
            selected = [int(c) for c in re.split(r'[,-]', cids) if c]
        except ValueError:
            return
        allowed = [c for c in selected if c in request.env.user.company_ids.ids]
        if allowed:
            request.update_context(allowed_company_ids=allowed)

    def _render(self, env, panels):
        own_roots, root_label = self._house_roots(env)
        payload = pipeline.build(self._iter_xmls(panels), own_roots, root_label)
        if payload is None:
            return ('<!DOCTYPE html><meta charset="utf-8"><body style="font-family:sans-serif">'
                    '<h2>Painel de Notas Fiscais (XML)</h2>'
                    '<p>Nenhum XML emitido pelas empresas da casa foi encontrado na base do NFe XML.</p>')
        _logger.info(
            'nfe_xml painel: %s notas, %s itens (recebidas ignoradas: %s, invalidas: %s, eventos: %s)',
            payload['meta']['n_notas'], payload['meta']['n_itens'],
            payload['meta'].get('recebidas'), payload['meta'].get('invalidas'), payload['meta'].get('eventos'))
        with file_open('liber_nfe_xml/static/panel/panel_template.html', 'r') as f:
            template = f.read()
        return template.replace('__PAYLOAD__', json.dumps(payload, ensure_ascii=False, separators=(',', ':')))

    @staticmethod
    def _iter_xmls(panels):
        # Batch the binary reads so the filestore blobs do not all sit in the
        # ORM cache at once (the base holds thousands of XMLs).
        for i in range(0, len(panels), 500):
            chunk = panels[i:i + 500]
            for rec in chunk:
                if not rec.file:
                    continue
                try:
                    yield base64.b64decode(rec.file), rec.id
                except Exception:
                    continue
            chunk.invalidate_recordset(['file'])

    @staticmethod
    def _house_roots(env):
        """8-digit CNPJ roots of every house company (sudo: the house is the
        whole database, regardless of the user's allowed companies)."""
        own_roots, root_label = set(), {}
        for company in env['res.company'].sudo().search([]):
            digits = re.sub(r'\D', '', company.partner_id.vat or '')
            if len(digits) == 14:
                root = digits[:8]
                own_roots.add(root)
                root_label.setdefault(root, company.name)
        return own_roots, root_label
