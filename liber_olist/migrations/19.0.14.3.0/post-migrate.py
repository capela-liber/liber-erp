# -*- coding: utf-8 -*-
"""O desconto do histórico sai do raw_json, não de mil chamadas à API.

O campo `valor_desconto` nasce vazio, e reler o detalhe de cada pedido para
preenchê-lo custaria 2,2 segundos por pedido — horas de API por um número que
já está guardado: o `raw_json` do espelho é a resposta inteira do Olist, e o
desconto está lá desde sempre. Ler dali é instantâneo e não gasta cota.

Sem isto, o Relatório mostraria desconto zero em todo o histórico e a coluna
nasceria mentindo.
"""
import json
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT id, raw_json FROM olist_order
         WHERE raw_json IS NOT NULL
           AND raw_json LIKE '%%valor_desconto%%'
           AND COALESCE(valor_desconto, 0) = 0
    """)
    achados, tocados = 0, []
    for oid, bruto in cr.fetchall():
        try:
            valor = (json.loads(bruto) or {}).get('valor_desconto')
        except (ValueError, TypeError):
            continue
        if isinstance(valor, str):
            try:
                valor = float(valor.strip().replace(',', '.') or 0)
            except ValueError:
                continue
        if not valor:
            continue
        cr.execute("UPDATE olist_order SET valor_desconto = %s WHERE id = %s",
                   (float(valor), oid))
        achados += 1
        tocados.append(oid)

    # O rateio nas LINHAS é campo armazenado, e SQL não dispara recompute: sem
    # isto o pedido saberia o desconto e o Relatório continuaria mostrando
    # zero — pior que não migrar, porque parece migrado.
    if tocados:
        env = api.Environment(cr, SUPERUSER_ID, {})
        linhas = env['olist.order'].browse(tocados).line_ids
        linhas.modified(['quantidade', 'valor_unitario'])
        env.flush_all()
    _logger.info("Olist: desconto recuperado do raw_json em %s pedido(s); "
                 "rateio recalculado em %s linha(s).",
                 achados, len(tocados) and len(
                     env['olist.order'].browse(tocados).line_ids))
