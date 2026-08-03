# -*- coding: utf-8 -*-
"""Adoção dos CFOPs que já existem, antes de carregar os do módulo.

A regra em si mora no `liber_nfe_xml`, junto com o modelo `nfe.cfop`: este
módulo não é o único a declarar CFOP em XML (o `liber_soc_audit` declara os
treze da consignação), e a regra que decide o que fazer com um código repetido
não pode ser propriedade de um dos declarantes. A história inteira está em
`liber_nfe_xml/cfop_adocao.py`.

Aqui fica só o que é deste módulo: quais arquivos ele declara.
"""

import os

from odoo.addons.liber_nfe_xml.cfop_adocao import preparar_cfops

DIRETORIO_DADOS = os.path.join(os.path.dirname(__file__), 'data')
# Só a tabela oficial do CONFAZ declara CFOPs. A configuração da casa mudou de
# lugar: mora em `nfe.operacao`, porque é atributo da operação e não do código.
ARQUIVOS_DADOS = ('nfe_cfop_oficial_data.xml',)
MODULO = 'liber_nfe_focus'


def preparar(env):
    """Mantida como ponto de entrada: a migração 19.0.1.2.0 chama por este nome."""
    preparar_cfops(env, MODULO, DIRETORIO_DADOS, ARQUIVOS_DADOS)


def pre_init_hook(env):
    preparar(env)


def post_init_hook(env):
    """As posições fiscais nascem com o módulo, já ligadas à operação.

    Nesta ordem, e a ordem importa: primeiro adota o que veio do legado (o banco
    migrado chega com mais de cem posições, todas sem operação), e só depois
    semeia -- assim a semeadura encontra os lugares ocupados e não cria a
    segunda posição para a mesma operação.
    """
    Posicao = env['account.fiscal.position']
    Posicao._nfe_adotar_posicoes_do_legado()
    Posicao._nfe_semear_posicoes()
