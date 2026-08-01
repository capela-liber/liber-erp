# -*- coding: utf-8 -*-
"""Adoção de CFOPs por código — a regra mora junto com o modelo.

O `nfe.cfop` é deste módulo, e mais de um módulo declara CFOPs em XML: o
`liber_soc_audit` traz os treze da consignação, o `liber_nfe_focus` traz a
tabela oficial inteira. São `xmlid` de módulos diferentes para o MESMO código
nacional — e o Odoo, vendo dois `xmlid`, cria dois registros.

Enquanto o código não era único, isso passava: sobravam pares de CFOP 5113 no
banco e a nota saía com a natureza de um ou de outro conforme a sorte do
`search`. Quando o `liber_nfe_focus` tornou o código único, o mesmo defeito
deixou de ser silencioso e virou `duplicate key` no meio da instalação — foi
assim que apareceu, em 31/07/2026, ao instalar a casa inteira num banco novo:
o focus entrou primeiro, carregou os 619 oficiais, e o `liber_soc_audit`
quebrou ao tentar criar o 5113 dele.

A saída não é um módulo ceder ao outro (a consignação não pode depender da
emissão fiscal, nem o contrário): é cada um **adotar** o CFOP que já existe
com aquele código, ganhando um segundo `xmlid` sobre o mesmo registro. Daí a
ordem de instalação deixa de importar, que é a única garantia que vale — não
existe "ordem certa" para se confiar num grafo de dependências.
"""

import logging
import os
from xml.etree import ElementTree

_logger = logging.getLogger(__name__)


def codigos_declarados(diretorio, arquivos):
    """(xmlid, código) de cada `nfe.cfop` declarado nos arquivos, sem repetir."""
    pares = {}
    for nome in arquivos:
        caminho = os.path.join(diretorio, nome)
        try:
            raiz = ElementTree.parse(caminho).getroot()
        except (OSError, ElementTree.ParseError) as exc:
            _logger.warning("Não deu para ler %s: %s", caminho, exc)
            continue
        for record in raiz.iter('record'):
            if record.get('model') != 'nfe.cfop':
                continue
            campo = record.find("field[@name='code']")
            if record.get('id') and campo is not None and campo.text:
                pares.setdefault(record.get('id'), campo.text.strip())
    return list(pares.items())


def deduplicar_cfops(env):
    """Funde CFOPs repetidos pelo código, mantendo o mais antigo.

    O CFOP é tabela nacional: dois registros com o mesmo código são sempre
    erro. Sobrevive o menor id, e todas as referências apontadas para os outros
    são remendadas antes de eles sumirem — inclusive os `xmlid`, que não são
    many2one e, se ficassem apontando para o registro que some, fariam o
    carregamento do XML tentar criar o CFOP de novo.

    A varredura é pelo registro de campos, não por uma lista escrita à mão:
    qualquer módulo que aponte para `nfe.cfop` entra junto, inclusive os que
    ainda não existem.
    """
    env.cr.execute("""
        SELECT code, array_agg(id ORDER BY id)
        FROM nfe_cfop WHERE code IS NOT NULL
        GROUP BY code HAVING count(*) > 1
    """)
    repetidos = env.cr.fetchall()
    if not repetidos:
        return

    campos = env['ir.model.fields'].sudo().search([
        ('ttype', '=', 'many2one'), ('relation', '=', 'nfe.cfop'),
        ('store', '=', True)])

    for code, ids in repetidos:
        fica, saem = ids[0], ids[1:]
        for campo in campos:
            modelo = env.get(campo.model)
            if modelo is None or not modelo._auto:
                continue
            coluna = campo.name
            if coluna not in modelo._fields:
                continue
            tabela = modelo._table
            env.cr.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = %s", (tabela, coluna))
            if not env.cr.fetchone():
                continue
            env.cr.execute(
                'UPDATE "%s" SET "%s" = %%s WHERE "%s" IN %%s'
                % (tabela, coluna, coluna), (fica, tuple(saem)))
        env.cr.execute(
            "UPDATE ir_model_data SET res_id = %s "
            "WHERE model = 'nfe.cfop' AND res_id IN %s", (fica, tuple(saem)))
        env.cr.execute("DELETE FROM nfe_cfop WHERE id IN %s", (tuple(saem),))
        _logger.info("CFOP %s: %d duplicata(s) fundida(s) em id %s.",
                     code, len(saem), fica)


def preparar_cfops(env, modulo, diretorio, arquivos):
    """Deixa a tabela pronta para receber os CFOPs declarados por `modulo`.

    Duas coisas, nesta ordem: funde os repetidos e dá `xmlid` do módulo aos
    que já existem — senão o XML os recria, e recriar viola a unicidade.

    Adota **só** os códigos que o módulo declara. Adotar os outros criaria
    vínculo de propriedade sobre CFOPs que não são dele, e desinstalar o
    módulo os apagaria junto.
    """
    deduplicar_cfops(env)
    Cfop = env['nfe.cfop']
    Dados = env['ir.model.data']
    adotados = 0
    for xmlid, codigo in codigos_declarados(diretorio, arquivos):
        if Dados.search_count([('module', '=', modulo), ('name', '=', xmlid),
                               ('model', '=', 'nfe.cfop')]):
            continue
        cfop = Cfop.search([('code', '=', codigo)], limit=1)
        if not cfop:
            continue  # não existe: o XML cria, e aí o xmlid nasce com ele
        Dados.create({
            'module': modulo,
            'name': xmlid,
            'model': 'nfe.cfop',
            'res_id': cfop.id,
            # noupdate False de propósito: é o que deixa o `-u` reaplicar a
            # configuração fiscal por cima, que é o comportamento desejado.
            'noupdate': False,
        })
        adotados += 1
    if adotados:
        _logger.info("Adotados %d CFOPs já existentes pelo %s.", adotados, modulo)
