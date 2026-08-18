# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Recarimba a situação dos pedidos que já existiam.

    O 12.7.0 criou a situação "Anterior ao corte", mas `state` é computado
    ARMAZENADO: o -u não recalcula linha antiga, e um banco com histórico
    (o staging tinha 777 pedidos pré-corte parados em "falta ler o detalhe")
    continuava mostrando fila de trabalho onde já era história. Recomputar
    uma vez resolve; daqui em diante os depends cuidam do resto.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    pedidos = env['olist.order'].search([])
    env.add_to_compute(env['olist.order']._fields['state'], pedidos)
    env['olist.order'].flush_model(['state'])
