# -*- coding: utf-8 -*-
"""O visitante da vitrine enxerga o balcão.

A demonstração pública abre em leitura toda tela que tem manual publicado. O
manual das feiras fala do CAIXA metade do tempo -- a mesa no cartão, o de-por,
o caixa de cada um -- e o aplicativo Ponto de Venda não aparecia para quem
entra na demonstração. Manual falando de uma tela que não existe é pior do que
não ter a tela.

O que ele ganha é o papel de USUÁRIO do PDV, que é o que faz o aplicativo e as
listas aparecerem. A gravação continua cortada um nível abaixo, na allowlist
do `liber_roles` (`ir.model.access.check`): ele vê os caixas da feira, vê o
que venderam e não abre sessão. É a mesma escolha que aquele módulo já
declara em voz alta -- assistente que abre e falha no Aplicar vale mais do que
menu que não abre, porque é uma demonstração.
"""
from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _liber_fairs_pos_ligar_no_visitante(self):
        visitante = self.env.ref('liber_roles.group_visitante',
                                 raise_if_not_found=False)
        pdv = self.env.ref('point_of_sale.group_pos_user',
                           raise_if_not_found=False)
        if not visitante or not pdv:
            return False
        visitante.sudo().implied_ids = [(4, pdv.id)]
        return True
