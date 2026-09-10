# -*- coding: utf-8 -*-
"""O campo "Canal" (tipo de evento) deixa de existir.

Eram dois campos chamados Canal, um debaixo do outro na mesma coluna: o tipo
de evento (Feira do livro, Evento próprio, Lançamento) e o canal de vendas.
Só o segundo conversa com o resto do sistema -- é ele que faz a feira
aparecer nos relatórios ao lado da Amazon e da distribuição.

A coluna continua no banco, com os valores que tinha. Odoo não apaga coluna
de campo removido, e apagar aqui seria jogar fora dado que ninguém pediu para
jogar fora: se o tipo de evento voltar um dia, o que estava lá ainda está.
Este script só conta o que sobrou, para o registro.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'event_fair' AND column_name = 'channel_type'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        SELECT channel_type, count(*) FROM event_fair
         WHERE channel_type IS NOT NULL GROUP BY 1 ORDER BY 2 DESC
    """)
    for tipo, quantas in cr.fetchall():
        print('liber_fairs: %s feira(s) eram "%s" (o valor fica na coluna)'
              % (quantas, tipo))
