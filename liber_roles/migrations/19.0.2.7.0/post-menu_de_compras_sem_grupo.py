# -*- coding: utf-8 -*-
"""Devolve `Compras ‣ Pedidos` a quem compra (24/08/2026).

O que aconteceu. Em 22/08 o Editorial ganhou leitura das POs, e para abrir o
caminho até a tela o `menu_compras_editorial.xml` somou
`group_editorial_assistente` em três menus: o raiz de Compras e os dois
filhos, `Pedidos` e `Pedidos de compra`.

No raiz a soma foi soma: o core já declara ali
`groups="group_purchase_manager,group_purchase_user"`, e acrescentar um
terceiro grupo não tira ninguém. Nos filhos foi subtração, porque no core eles
NÃO têm grupo nenhum -- e menu sem grupo é aberto a quem alcança o pai e lê o
modelo da ação. Ao ganhar o primeiro grupo, os dois passaram a ser só do
Editorial. O Financeiro, que é o dono do processo de compra, abria o app e via
`Produtos` e nada mais.

Por que isto é migração e não bastou tirar as linhas do XML. É o mesmo motivo
de sempre neste módulo: `group_ids` é uma m2m escrita por comando incremental.
Apagar o `<record>` faz o Odoo parar de reescrever a aresta -- não a apaga de
onde já foi escrita. Sem esta passagem, dev, staging e prod continuariam com o
menu fechado, e o conserto existiria só no repositório.

A régua é estreita: tira SÓ o `group_editorial_assistente`, e SÓ desses dois
menus. Se alguém tiver posto outro grupo ali na mão, essa é decisão de outra
pessoa e não cabe a uma migração desfazê-la -- e, tendo outro grupo, o menu
segue fechado, o que este script então denuncia no log em vez de corrigir em
silêncio.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MENUS = (
    'purchase.menu_procurement_management',
    'purchase.menu_purchase_form_action',
)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    editorial = env.ref('liber_roles.group_editorial_assistente',
                        raise_if_not_found=False)
    if not editorial:
        return

    for xmlid in MENUS:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if not menu or editorial not in menu.group_ids:
            continue
        menu.write({'group_ids': [(3, editorial.id)]})
        if menu.group_ids:
            _logger.warning(
                "%s continua restrito a %s: o menu do core é aberto, e quem "
                "não estiver nesses grupos segue sem o caminho até a tela.",
                xmlid, ', '.join(menu.group_ids.mapped('name')))
        else:
            _logger.info("%s voltou a ser aberto, como no core.", xmlid)
