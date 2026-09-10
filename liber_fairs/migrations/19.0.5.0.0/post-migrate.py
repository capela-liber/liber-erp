# -*- coding: utf-8 -*-
"""A série do evento passa de E00001 para EV/ANO/00001.

A sequência está em `noupdate`, e com razão: número de documento não se
reescreve por atualização de módulo. Mas a FORMA mudou (E confundia com os
pedidos B e C), e a série ainda não numerou nada que valha história — por
isso ela é corrigida aqui, uma vez.

O que JÁ foi numerado fica como está: documento emitido não muda de nome. Se
houver evento antigo com E00001, ele continua E00001, e os novos nascem
EV/ANO/NNNNN.
"""


def migrate(cr, version):
    # O prefixo vai como VALOR ligado, e não dentro do texto do SQL: o
    # psycopg2 não desescapa `%%` quando não há parâmetro, e a série nascia
    # com `EV/%%(year)s/` literal -- o número saía com o `%%(year)s` no meio.
    cr.execute("""UPDATE ir_sequence
                     SET prefix = %s, name = 'Event (EV)',
                         use_date_range = true
                   WHERE code = 'event.fair' AND prefix IN ('E', 'EV/%%(year)s/')""",
               ('EV/%(year)s/',))
    print('série do evento atualizada: %s' % cr.rowcount)
