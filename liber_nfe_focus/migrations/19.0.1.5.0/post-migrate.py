# -*- coding: utf-8 -*-
"""As posições fiscais herdadas ganham a operação, e o nome da casa.

O banco migrado chega com 111 posições fiscais vindas do legado e **nenhuma**
ligada a uma operação: lá elas eram rótulo, não mecanismo. O nome carregava
tudo o que não tinha onde morar -- a letra da casa, o nome da empresa, o par de
CFOPs e um asterisco.

Aqui o nome vira só nome. A letra fica (é a taxonomia da casa e é boa), o par de
CFOPs volta num formato só, e o resto sai. A operação, que era o que o nome
estava tentando dizer, passa a estar num campo.

Depois disso a semeadura completa o que faltar: operação da casa que nenhuma
posição herdada cobria ganha a sua, em todas as empresas brasileiras.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    Posicao = env['account.fiscal.position']

    adotadas, renomeadas, sem_operacao = Posicao._nfe_adotar_posicoes_do_legado()
    criadas = Posicao._nfe_semear_posicoes()

    _logger.info(
        "liber_nfe_focus 19.0.1.5.0: %d posições adotadas do legado, "
        "%d renomeadas, %d criadas; %d ficaram sem operação (o nome não "
        "declara CFOP dedutível) e seguem como estavam.",
        len(adotadas), len(renomeadas), len(criadas), len(sem_operacao))
    for posicao in sem_operacao:
        _logger.info("  sem operação: [%s] %s",
                     posicao.company_id.name, posicao.name)
