# -*- coding: utf-8 -*-
"""A operação no imposto — que é por onde a posição fiscal a entrega.

Este desenho não foi inventado aqui: é o que o sistema em produção faz há três
anos. No `hedra_legacy`, `account_tax.edoo_cfop_id` marca 66 impostos com nomes
como `ICMS 41 - CFOP 5101 - EDLAB`, alíquota **zero** — eles não existem para
tributar, existem para **carregar a marcação fiscal**. Cruzando as 14.555 notas
autorizadas com o imposto de cada linha, o CFOP bate em **109.368 de 110.480**
linhas (99%).

A diferença aqui é que o imposto aponta para a **operação**, não para um CFOP
inteiro. O legado precisava de dois impostos por operação — um 5xxx e um 6xxx —
e de alguém para escolher o certo conforme o estado do cliente. Apontando para
a operação, o imposto é um só e o primeiro dígito nasce do destino.
"""

from odoo import fields, models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    nfe_operacao_id = fields.Many2one(
        'nfe.operacao', string='Operação fiscal',
        help="A operação que este imposto representa. É o caminho pelo qual a "
             "posição fiscal a entrega à nota: trocar a posição troca o "
             "imposto, e a operação vem junto.\n\n"
             "O CFOP completo sai daqui mais o destino — 5xxx dentro do "
             "estado, 6xxx para fora. Um imposto por operação, não dois.")
