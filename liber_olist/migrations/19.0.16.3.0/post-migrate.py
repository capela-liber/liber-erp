# -*- coding: utf-8 -*-
"""O canal de venda vai para as notas que já estavam ligadas a um pedido.

Até esta versão o espelho carimbava o canal no pedido de venda e na fatura,
nunca na NFe -- e é a NFe que o Painel de Vendas lê. O histórico inteiro
estava num "Nenhum": no `dev` de 06/09/2026, 257 das 286 notas ligadas a
pedido com canal. Este acerto escreve o canal do pedido em toda nota ligada
que ainda não tem canal; nota com canal já posto fica como está.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    pedidos = env['olist.order'].with_context(active_test=False).search([
        ('team_id', '!=', False), ('nfe_panel_id', '!=', False),
        ('nfe_panel_id.team_id', '=', False)])
    notas = pedidos._carimbar_canal_na_nota()
    _logger.info("Olist: canal de venda escrito em %s nota(s) que estavam "
                 "sem canal.", len(notas))
