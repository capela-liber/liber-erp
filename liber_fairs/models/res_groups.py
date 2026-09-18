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
        planner = ref('liber_fairs.group_fair_planner', raise_if_not_found=False)
        if not user or not manager or not planner:
            return False
        # Quem está na praça com o celular é o assistente comercial: lança
        # contagem, fecha o dia, despacha reposição. A logística entra como
        # usuária porque é ela quem separa, embala e confere o retorno.
        #
        # ABRIR a feira era só do gerente, pelo mesmo motivo do contrato de
        # consignação: planejar um evento compromete estoque da casa fora da
        # casa. Deixou de ser (15/09/2026, decisão do dono): a feira nasce da
        # agenda comercial, e quem a agenda é quem fala com a praça. Segurar
        # a criação no gerente fazia o assistente pedir por e-mail o que ele
        # mesmo já vai operar do começo ao fim. O Comercial é equipe interna
        # da casa -- o cerco que existe nas feiras é contra o balcão
        # (atendente e supervisor), não contra quem planeja daqui.
        #
        # A LOGÍSTICA continua só operando: ela separa e confere o que o
        # Comercial decidiu mandar. Quem abre evento é quem o vende.
        #
        # O assistente entra como PLANEJADOR, não como administrador: duas
        # coisas ficam resguardadas no gerente -- apagar a feira (que já tem
        # analítico e movimento de estoque atrás dela) e decidir quanto a
        # equipe ganha (combinação anterior ao evento, e ninguém decide a
        # própria diária).
        mapa = [
            ('liber_roles.group_comercial_assistente', planner),
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
        # O VISITANTE da demonstração pública abre em leitura toda tela que
        # tem manual publicado, e Eventos passou a ter um. Sem isto, quem
        # entra na vitrine lê o manual da feira e não acha o aplicativo --
        # que é pior do que não ter o módulo. A escrita não vem junto: a
        # trava do visitante é no ORM, não no menu.
        #
        # O papel de USUÁRIO, e não o de administrador: o visitante olha, e
        # planejar feira é escrever.
        visitante = ref('liber_roles.group_visitante', raise_if_not_found=False)
        if visitante:
            visitante.sudo().implied_ids = [(4, user.id)]
        return True
