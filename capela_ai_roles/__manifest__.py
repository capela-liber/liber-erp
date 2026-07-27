# -*- coding: utf-8 -*-
{
    'name': 'Capela AI × Liber Roles (a ponte)',
    'version': '19.0.1.0.0',
    'summary': 'Casa as ferramentas do agente com as funções da casa',
    'description': """
Doze linhas de dado que fazem o `capela_ai` conhecer as funções do
`liber_roles`. Existe como módulo separado por um motivo de negócio, não de
engenharia: o `liber_*` é o que liberamos de graça e o `capela_*` é o que se
vende. Se o núcleo do agente dependesse do `liber_roles`, ele não poderia ser
instalado numa casa que usa os perfis nativos do Odoo -- e é justamente essa
casa que a gente quer poder atender.

Então o núcleo oferece o mecanismo (campos em `res.groups`) e esta ponte
escolhe os números:

    Assistente   10 documentos por plano
    Gerente      50
    Direção      50, mas só consulta -- a Direção lê largo e não opera
    Visitante     0, e isso é uma linha que se escreve por extenso

O visitante não aparece neste arquivo, e a ausência é deliberada: ele é a conta
da apresentação pública, que não grava nem pelo Odoo (ver o guarda do
`liber_roles`) e muito menos pelo agente. Não conceder é a decisão; não há nada
a manter.

As concessões são somadas, não substituídas -- (4, ref(...)) e não (6, 0, ...).
Uma atualização do módulo acrescenta o que faltava sem apagar o que um
administrador tenha concedido a mais na tela. O preço é que revogar exige tirar
na tela também, e não basta editar este arquivo.
""",
    'author': 'EdLab Press',
    'category': 'Productivity',
    'depends': [
        'capela_ai',
        'liber_roles',
    ],
    'data': [
        'data/capela_ai_roles_data.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'OEEL-1',
}
