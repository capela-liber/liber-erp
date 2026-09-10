# -*- coding: utf-8 -*-
"""O estado "Em curso" deixa de existir.

Ele existia para separar "os livros estão na estrada" de "o evento abriu",
e a única forma de alcançá-lo era um botão Começar que o dono da casa
perguntou para que servia -- pergunta que já é a resposta. Nenhuma regra
dependia do estado, e quem sabe se a feira abriu é o calendário, não um
clique.

Feira que estava Em curso passa a Enviada, que é o que ela é: os livros
saíram e ainda não voltaram. Sem esta passagem, o registro fica com um valor
que a Selection não conhece mais, e a tela mostra o campo vazio.
"""


def migrate(cr, version):
    cr.execute("UPDATE event_fair SET state = 'shipped' WHERE state = 'running'")
    if cr.rowcount:
        print('liber_fairs: %s feira(s) de "Em curso" para "Enviado"' % cr.rowcount)
