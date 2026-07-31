# -*- coding: utf-8 -*-
"""Adoção dos CFOPs que já existem, antes de carregar os do módulo.

O `liber_nfe_xml` cria CFOPs por código, em Python (`classify_cfops`), e por
isso eles não têm `xmlid`. Um `<record id="cfop_5101">` num banco desses criaria
um **segundo** 5101 em vez de completar o que está lá — e aí a nota passaria a
depender de qual dos dois o usuário escolheu.

Este gancho roda antes do carregamento dos dados e dá aos CFOPs existentes o
`xmlid` que o XML vai procurar. A partir daí o `-u` atualiza em vez de duplicar,
que é o ponto de a configuração fiscal viver no código: ela sobrevive às
migrações seguintes em vez de ser refeita a cada uma.

Adota **só** os códigos que o módulo declara. Adotar os outros criaria vínculo
de propriedade sobre CFOPs que não são nossos — e desinstalar o módulo os
apagaria junto.
"""

import logging
import os
from xml.etree import ElementTree

_logger = logging.getLogger(__name__)

DIRETORIO_DADOS = os.path.join(os.path.dirname(__file__), 'data')
# Só a tabela oficial do CONFAZ declara CFOPs. A configuração da casa mudou de
# lugar: mora em `nfe.operacao`, porque é atributo da operação e não do código.
ARQUIVOS_DADOS = ('nfe_cfop_oficial_data.xml',)
MODULO = 'liber_nfe_focus'


def _codigos_declarados():
    """(xmlid, código) de cada CFOP que o módulo define, sem repetir."""
    pares = {}
    for nome in ARQUIVOS_DADOS:
        caminho = os.path.join(DIRETORIO_DADOS, nome)
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


def _deduplicar_cfops(env):
    """Funde CFOPs repetidos pelo código, antes de o código virar único.

    O CFOP é tabela nacional: dois registros com o mesmo código são sempre erro,
    e um erro silencioso — quem escolhe na tela não vê diferença, e a nota sai
    com a natureza de um ou de outro conforme a sorte do `search`. O staging
    tinha sete pares assim.

    Sobrevive o mais antigo (menor id), e todas as referências apontadas para os
    outros são remendadas antes de eles sumirem. A varredura é pelo registro de
    campos, não por uma lista escrita à mão: qualquer módulo que aponte para
    `nfe.cfop` entra junto, inclusive os que ainda não existem.
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
        # O xmlid também aponta, e ele não é um many2one: se ficar apontando
        # para o registro que some, o carregamento do XML tenta CRIAR o CFOP de
        # novo -- e agora o código é único, então o módulo inteiro não sobe.
        env.cr.execute(
            "UPDATE ir_model_data SET res_id = %s "
            "WHERE model = 'nfe.cfop' AND res_id IN %s", (fica, tuple(saem)))
        env.cr.execute("DELETE FROM nfe_cfop WHERE id IN %s", (tuple(saem),))
        _logger.info("CFOP %s: %d duplicata(s) fundida(s) em id %s.",
                     code, len(saem), fica)


def preparar_cfops(env):
    """Deixa a tabela de CFOPs pronta para receber os dados do módulo.

    Duas coisas, nesta ordem, e as duas necessárias: funde os repetidos (o
    código vai virar único) e dá `xmlid` aos que já existem (senão o XML os
    recria, e agora recriar é violar a unicidade).

    Chamada de dois lugares -- `pre_init_hook` para quem instala, e a migração
    19.0.1.2.0 para quem já tinha o módulo. Quem só atualiza nunca passa pelo
    hook, e foi exatamente aí que isto quebrou primeiro.
    """
    _deduplicar_cfops(env)
    Cfop = env['nfe.cfop']
    Dados = env['ir.model.data']
    adotados = 0
    for xmlid, codigo in _codigos_declarados():
        ja_tem = Dados.search_count([
            ('module', '=', MODULO), ('name', '=', xmlid),
            ('model', '=', 'nfe.cfop')])
        if ja_tem:
            continue
        cfop = Cfop.search([('code', '=', codigo)], limit=1)
        if not cfop:
            continue  # não existe: o XML cria, e aí o xmlid nasce com ele
        Dados.create({
            'module': MODULO,
            'name': xmlid,
            'model': 'nfe.cfop',
            'res_id': cfop.id,
            # noupdate False de propósito: é o que deixa o `-u` reaplicar a
            # configuração fiscal por cima, que é o comportamento desejado.
            'noupdate': False,
        })
        adotados += 1
    if adotados:
        _logger.info("Adotados %d CFOPs já existentes pelo %s.", adotados, MODULO)


def pre_init_hook(env):
    preparar_cfops(env)
