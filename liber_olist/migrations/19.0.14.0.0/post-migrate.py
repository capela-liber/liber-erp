# -*- coding: utf-8 -*-
"""O corte saiu (22/08/2026): pedido que era 'anterior_corte' volta à régua.

O estado é compute armazenado — sem isto os registros antigos ficariam
carimbados com um vocabulário que o módulo já não fala. A recomputação os
devolve ao trilho normal: sem detalhe, a importar, ou importado. O que a
casa decidir ignorar do histórico se resolve pelo Arquivar, que é gesto de
gente e reversível.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT id FROM olist_order WHERE state = 'anterior_corte'
    """)
    ids = [r[0] for r in cr.fetchall()]
    if not ids:
        return
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    pedidos = env['olist.order'].browse(ids)
    pedidos.modified(['detalhe_lido_em'])   # derruba o compute armazenado
    pedidos._compute_state()
    env.flush_all()
