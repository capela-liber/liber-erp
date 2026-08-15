# -*- coding: utf-8 -*-
import base64
import json
import logging
import re

from markupsafe import escape

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
        house = self._house_roots(env)
        # The house roots join the signature: fixing a company's CNPJ changes
        # what the panel accepts without touching a single NFe record, and the
        # stale entry would otherwise survive it.
        sig = (env.uid, companies, len(panels),
               max(panels.mapped('write_date'), default=None), tuple(sorted(house[0])))
        key = (env.cr.dbname, companies)
        cached = _CACHE.get(key)
        if cached and cached[0] == sig:
            html = cached[1]
        else:
            html = self._render(env, panels, house)
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

    def _render(self, env, panels, house):
        own_roots, root_label, sem_cnpj = house
        stats = {}
        payload = pipeline.build(self._iter_xmls(panels), own_roots, root_label, stats)
        if payload is None:
            _logger.warning(
                'nfe_xml painel: nada a analisar em %s notas (raizes da casa: %s; '
                'empresas sem CNPJ: %s; parse: %s)',
                len(panels), sorted(own_roots) or 'NENHUMA',
                [n for n, _v in sem_cnpj] or 'nenhuma',
                {k: v for k, v in stats.items() if k != 'emissores'})
            return self._empty_page(len(panels), own_roots, root_label, sem_cnpj, stats)
        _logger.info(
            'nfe_xml painel: %s notas, %s itens (recebidas ignoradas: %s, invalidas: %s, eventos: %s)',
            payload['meta']['n_notas'], payload['meta']['n_itens'],
            payload['meta'].get('recebidas'), payload['meta'].get('invalidas'), payload['meta'].get('eventos'))
        with file_open('liber_nfe_xml/static/panel/panel_template.html', 'r') as f:
            template = f.read()
        return template.replace('__PAYLOAD__', json.dumps(payload, ensure_ascii=False, separators=(',', ':')))

    @staticmethod
    def _empty_page(n_panels, own_roots, root_label, sem_cnpj, stats):
        """Empty state that says why it is empty.

        The panel is seller-centric: a note only enters the analysis when its
        issuer CNPJ root belongs to a house company. When that never happens
        the cause is almost always the company register, not the XMLs - so
        show both sides (roots we looked for, roots the notes actually carry).
        """
        e = escape
        roots = ''.join(
            f'<li><code>{e(r)}</code> — {e(root_label.get(r) or "")}</li>'
            for r in sorted(own_roots)) or '<li><em>nenhuma</em></li>'
        pendentes = ''.join(
            f'<li>{e(name)} — {e(vat) if vat else "<em>sem documento</em>"}</li>'
            for name, vat in sem_cnpj)
        emissores = ''.join(
            f'<tr><td><code>{e(x["raiz"])}</code></td><td>{e(x["nome"])}</td>'
            f'<td style="text-align:right">{x["n"]}</td></tr>'
            for x in stats.get('emissores') or [])
        aviso = ''
        if pendentes and emissores:
            aviso = ('<p class="warn">Se alguma raiz da tabela acima é de uma empresa da casa, '
                     'o CNPJ dela não está no cadastro da empresa — corrija em '
                     '<b>Configurações → Empresas</b> e reimporte/reidentifique as notas.</p>')
        return f"""<!DOCTYPE html><meta charset="utf-8">
<title>Painel de Notas Fiscais (XML)</title>
<body style="font-family:system-ui,sans-serif;max-width:52em;margin:2em auto;line-height:1.5;color:#222">
<h2>Painel de Notas Fiscais (XML)</h2>
<p>Nenhum XML <b>emitido pelas empresas da casa</b> foi encontrado — o painel é
do lado vendedor, então notas recebidas de terceiros ficam de fora.</p>
<h3>O que foi lido</h3>
<ul>
 <li>{n_panels} registro(s) de NFe XML visíveis nas empresas selecionadas</li>
 <li>{stats.get('recebidas', 0)} descartada(s) por serem de emissor de fora da casa</li>
 <li>{stats.get('invalidas', 0)} XML(s) ilegível(is), {stats.get('eventos', 0)} evento(s)</li>
</ul>
<h3>Raízes de CNPJ tidas como da casa</h3>
<ul>{roots}</ul>
{f'<h3>Empresas ignoradas (documento não é CNPJ)</h3><ul>{pendentes}</ul>' if pendentes else ''}
{f'<h3>Emissores das notas descartadas</h3><table cellpadding="4" style="border-collapse:collapse"><tr><th align="left">Raiz</th><th align="left">Nome no XML</th><th>Notas</th></tr>{emissores}</table>' if emissores else ''}
{aviso}
<style>code{{background:#f2f2f2;padding:0 .3em}} .warn{{background:#fff4d6;padding:.8em 1em;border-left:3px solid #e0a800}} th,td{{border-bottom:1px solid #ddd}}</style>
"""

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
        whole database, regardless of the user's allowed companies).

        Also returns the companies whose registered document is not a CNPJ
        (blank, or a CPF): those are invisible to the analysis, and a company
        that issues NFe under a CNPJ absent from this set drops out of the
        panel entirely.
        """
        own_roots, root_label, sem_cnpj = set(), {}, []
        for company in env['res.company'].sudo().search([]):
            vat = company.partner_id.vat or ''
            digits = re.sub(r'\D', '', vat)
            if len(digits) == 14:
                root = digits[:8]
                own_roots.add(root)
                root_label.setdefault(root, company.name)
            else:
                sem_cnpj.append((company.name, vat))
        return own_roots, root_label, sem_cnpj
