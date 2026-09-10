# -*- coding: utf-8 -*-
"""Pendura as feiras nos perfis da casa sem inverter a dependência.

O liber_roles não pode depender deste módulo (ele é o alicerce dos perfis e
carrega antes de tudo). Quem se pendura nele somos nós, por <function> no fim
do data -- mesmo desenho do capela_influencers. Se o liber_roles não estiver
instalado, cada ref falha calada e o método não faz nada.
"""
from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _liber_fairs_ligar_nos_departamentos(self):
        ref = self.env.ref
        user = ref('liber_fairs.group_fair_user', raise_if_not_found=False)
        manager = ref('liber_fairs.group_fair_manager', raise_if_not_found=False)
        if not user or not manager:
            return False
        # Quem está na praça com o celular é o assistente comercial: lança
        # contagem, fecha o dia, despacha reposição. Quem abre e fecha a feira
        # é o gerente. A logística entra como usuária porque é ela quem
        # separa, embala e confere o retorno.
        mapa = [
            ('liber_roles.group_comercial_assistente', user),
            ('liber_roles.group_logistica_assistente', user),
            ('liber_roles.group_comercial_gerente', manager),
            ('liber_roles.group_logistica_gerente', manager),
        ]
        for xmlid, grupo in mapa:
            papel = ref(xmlid, raise_if_not_found=False)
            if papel:
                papel.sudo().implied_ids = [(4, grupo.id)]
        # A regra da casa: a Direção alcança tudo o que qualquer perfil
        # alcança, e há teste de superconjunto no liber_roles que quebra se
        # alguém esquecer.
        direcao = ref('liber_roles.group_direcao', raise_if_not_found=False)
        if direcao:
            direcao.sudo().implied_ids = [(4, manager.id)]
        return True
