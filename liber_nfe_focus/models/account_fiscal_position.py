# -*- coding: utf-8 -*-
"""A operação fiscal na posição fiscal — a ligação direta, e a que se vê.

A posição fiscal SEMPRE decidiu a operação; ela só o fazia por um caminho
indireto, pelo imposto que substituía. Isso funciona (é o que o sistema em
produção faz em 110 mil linhas) mas obriga a abrir o imposto para descobrir que
CFOP vai sair, e a confiar que ninguém trocou o imposto no meio.

Aqui a posição fiscal diz a operação em voz alta. O caminho pelo imposto
continua valendo, e continua ganhando quando existe: ele é POR LINHA, e uma nota
pode misturar operações -- consignação e bonificação na mesma remessa. A posição
fiscal é do cabeçalho, e cabeçalho não desempata linha.
"""

from odoo import api, fields, models


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    nfe_operacao_id = fields.Many2one(
        'nfe.operacao', string='Operação fiscal',
        help="A operação que esta posição fiscal representa. O CFOP completo "
             "nasce dela mais o endereço do cliente — 5xxx dentro do estado, "
             "6xxx para fora.\n\n"
             "Um imposto que carregue operação própria ganha desta, porque o "
             "imposto é por linha e a posição fiscal é da nota inteira.")
    nfe_cfop_interno_id = fields.Many2one(
        'nfe.cfop', string='CFOP dentro do estado',
        compute='_compute_nfe_cfops', help="Só leitura: sai da operação.")
    nfe_cfop_externo_id = fields.Many2one(
        'nfe.cfop', string='CFOP para outro estado',
        compute='_compute_nfe_cfops', help="Só leitura: sai da operação.")

    @api.depends('nfe_operacao_id')
    def _compute_nfe_cfops(self):
        for posicao in self:
            operacao = posicao.nfe_operacao_id
            posicao.nfe_cfop_interno_id = operacao.cfop_record('interna')
            posicao.nfe_cfop_externo_id = operacao.cfop_record('interestadual')
