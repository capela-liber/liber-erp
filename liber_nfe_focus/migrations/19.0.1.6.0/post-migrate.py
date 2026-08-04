# -*- coding: utf-8 -*-
"""As doze que faltavam ganham operação, e o resto da lista ganha letra.

A migração 19.0.1.5.0 adotou o que podia adotar e parou onde tinha que parar:
doze posições escreviam o CFOP no próprio nome -- "CFOP: 1917", "CFOP 1914/2914",
"CFOP 5209/6209" -- e ficaram sem operação porque **a operação não existia na
casa**. As três nascem nesta versão (entrada 917, entrada 914, saída 209), então
aqui basta reabrir a adoção: ela reencontra as mesmas doze e agora as liga.

O que sobra depois disso não é resíduo. É o IRRF do direito autoral, o serviço
da Logopoiese, o cupom ao consumidor, e um punhado de posição financeira ou
genérica. Nenhuma emite NFe modelo 55, nenhuma tem CFOP, e nenhuma deveria
receber uma operação inventada. O que elas recebem é a letra -- para que a
lista de posições fiscais se leia inteira pelo mesmo alfabeto.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    Posicao = env['account.fiscal.position']

    # A ordem é a mesma da 19.0.1.5.0, e por isso mesmo: adotar primeiro deixa
    # a posição herdada ocupar o lugar da que nasceria na semeadura; semear
    # depois dá às três operações novas a sua posição nas empresas que não
    # herdaram nenhuma; letrar por último pega o que sobrou dos dois.
    adotadas, renomeadas, sem_operacao = Posicao._nfe_adotar_posicoes_do_legado()
    criadas = Posicao._nfe_semear_posicoes()
    letradas = Posicao._nfe_letrar_sem_operacao()

    _logger.info(
        "liber_nfe_focus 19.0.1.6.0: %d posições ganharam operação agora que "
        "entrada 917, entrada 914 e saída 209 existem (%d renomeadas), "
        "%d criadas; %d seguem sem operação, e dessas %d foram postas no "
        "alfabeto.",
        len(adotadas), len(renomeadas), len(criadas), len(sem_operacao),
        len(letradas))
    for posicao in letradas:
        _logger.info("  letrada: [%s] %s", posicao.company_id.name, posicao.name)
