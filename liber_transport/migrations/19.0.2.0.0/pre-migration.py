# -*- coding: utf-8 -*-
"""19.0.1 -> 19.0.2: a solicitação de coleta virou lote (COL/).

O e-mail deixou de ser renderizado sobre um registro temporário do
assistente e passou a ser renderizado sobre `liber.transport.pickup.request`,
o lote que sobrevive ao clique. O template precisa acompanhar a mudança de
modelo, mas ele nasceu num bloco `noupdate="1"` — e o Odoo guarda essa marca
em `ir_model_data`, não no arquivo. Enquanto ela estiver de pé, a atualização
passa ao largo do registro e o template continua apontando para um modelo que
já não recebe nada: o envio morre com "Failed to render".

Soltar a marca aqui (antes da carga dos dados) deixa o próprio upgrade
reescrever o template. O que a casa edita — o texto de abertura — não mora no
template, mora nas Definições, por empresa; então nada de ninguém se perde.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = false
         WHERE module = 'liber_transport'
           AND name = 'mail_template_pickup_request'
    """)
