# -*- coding: utf-8 -*-
"""O nome dos menus em pt_BR, que a tradução normal não alcança.

O `views/rotulos_canal.xml` já reescreve o nome dos dois menus que levam à
lista de canais -- mas escreve o FONTE (en_US). O valor em pt_BR continua sendo
o que o `.po` do `sale` gravou um dia ("Equipes de vendas"), e ele ganha da
fonte na hora de mostrar.

E não dá para consertar pelo `.po` deste módulo: o registro do menu pertence ao
`sale`, então o exportador de tradução nunca o atribui a nós. Nem o
`--i18n-overwrite` pega -- nome de menu, de modelo e de ação são a exceção
conhecida (a mesma que já mordeu em "Devoluções" e "Acertos").

Sobra escrever direto, e é o que este hook faz na instalação. Fica estável: um
`-u` do `sale` não sobrescreve tradução existente, e um banco recriado do zero
reinstala este módulo e passa por aqui de novo.
"""
import logging

_logger = logging.getLogger(__name__)

MENUS_EM_PT_BR = {
    'sale.sales_team_config': 'Canais de Vendas',
    'sale.report_sales_team': 'Canais de Vendas',
}


def post_init_hook(env):
    for xmlid, nome in MENUS_EM_PT_BR.items():
        menu = env.ref(xmlid, raise_if_not_found=False)
        if not menu:
            continue
        menu.with_context(lang='pt_BR').name = nome
        _logger.info("liber_partner_commercial: menu %s em pt_BR -> %s", xmlid, nome)
