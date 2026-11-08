# -*- coding: utf-8 -*-
"""O desconto do Olist vai para os pedidos de venda já importados.

Até esta versão o pedido de venda nascia com o preço bruto e desconto zero --
ou com o desconto da lista de preços do parceiro, que o Olist não deu. O
Painel lia o pedido e mostrava a venda do site sem o desconto (a Vivi achou
no S67320: 286,06 no Painel, 230,66 de mercadoria na nota). No `dev` de
29/10/2026: 58 pedidos sem o desconto do Olist e 18 com desconto de lista.

A fatura não se toca: ela nasce do XML e já dizia o desconto.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    pedidos = env['olist.order'].with_context(active_test=False).search([
        ('sale_order_id', '!=', False), ('e_bonificacao', '=', False)])
    linhas = pedidos._acertar_desconto_no_pedido()
    _logger.info("Olist: desconto acertado em %s linha(s) de %s pedido(s) "
                 "de venda.", len(linhas), len(linhas.order_id))
