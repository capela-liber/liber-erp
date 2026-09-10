# -*- coding: utf-8 -*-
"""Marca os tipos de operação de caixa que já existiam.

A marca nasceu depois deles, e sem ela os caixas de feiras já encerradas
continuariam desenhando cartão na Visão geral do Inventário.
"""


def migrate(cr, version):
    cr.execute("""UPDATE stock_picking_type
                     SET is_fair_register = true
                   WHERE is_fair_register IS NOT TRUE
                     AND (fair_id IS NOT NULL
                          OR sequence_code LIKE 'PDV%%'
                          OR sequence_code LIKE 'FPDV%%')""")
    print('tipos de caixa marcados: %s' % cr.rowcount)
