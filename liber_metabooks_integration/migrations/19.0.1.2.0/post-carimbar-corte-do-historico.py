"""A linha na areia: tudo o que veio até agora fica para trás.

`metabooks_export_last_track` é onde o chatter começa a valer para a planilha,
e só era carimbado quando um lote saía. Livro que **veio** da Metabooks nunca
saiu daqui, então o corte ficou em zero e o export propunha devolver a
biografia inteira do registro -- no 1964 (9788577154036), 16 das 19 alterações
eram a importação de 04/08 e a ficha técnica de 11/08, lidas deles.

Daqui para a frente o carimbo é automático: toda escrita sob
`metabooks_from_sync` avança o corte (ver `_metabooks_settle_history`). Este
passo resolve o passado do único jeito honesto disponível -- de uma vez, para
todos --, porque separar retroativamente edição da casa de dado deles exigiria
reler livro a livro na API, e a decisão foi seguir daqui para a frente.

O PREÇO, dito com todas as letras: alteração legítima ainda não enviada some
da fila junto. Quem tiver edição pendente que importe, refaça depois deste
passo.
"""


def migrate(cr, version):
    cr.execute("SELECT coalesce(max(id), 0) FROM mail_tracking_value")
    corte = cr.fetchone()[0]

    cr.execute("""
        UPDATE product_template
           SET metabooks_export_last_track = %s
         WHERE coalesce(metabooks_export_last_track, 0) < %s
    """, (corte, corte))
    carimbados = cr.rowcount

    cr.execute("""
        UPDATE product_template
           SET metabooks_export_pending = false,
               metabooks_export_pending_since = NULL
         WHERE metabooks_export_pending
    """)
    print('Metabooks: corte em %s, %s livro(s) carimbado(s), %s saíram da fila'
          % (corte, carimbados, cr.rowcount))
