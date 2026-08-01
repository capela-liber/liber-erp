# -*- coding: utf-8 -*-
"""Adoção dos CFOPs da consignação que já existem no banco.

Os treze CFOPs deste módulo são da tabela nacional, e por isso podem já estar
no banco antes dele: postos pelo `liber_nfe_xml` (que os cria por código, em
Python, sem `xmlid`) ou pelo `liber_nfe_focus`, que carrega a tabela oficial
inteira. Nos dois casos, criar um segundo registro com o mesmo código é erro —
e desde que o código virou único, é erro que derruba a instalação.

Sem este gancho, instalar a casa inteira num banco novo funcionava ou não
conforme a ordem em que o Odoo resolvesse o grafo de dependências: com o focus
antes, o carregamento daqui morria com `duplicate key` no CFOP 5113. Ordem de
instalação não é garantia de nada, e não é sobre ela que se constrói.

A regra mora no `liber_nfe_xml`, com o modelo. Aqui só o que é deste módulo.
"""

import os

from odoo.addons.liber_nfe_xml.cfop_adocao import preparar_cfops

DIRETORIO_DADOS = os.path.join(os.path.dirname(__file__), 'data')
ARQUIVOS_DADOS = ('nfe_cfop_consignment_data.xml',)
MODULO = 'liber_soc_audit'


def pre_init_hook(env):
    preparar_cfops(env, MODULO, DIRETORIO_DADOS, ARQUIVOS_DADOS)
