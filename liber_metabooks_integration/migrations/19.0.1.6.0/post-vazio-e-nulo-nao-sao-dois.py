"""Texto vazio vira nulo: um grupo "vazio" só, e o kanban para de morrer.

Agrupar o kanban de Livros pela Coleção derrubava a tela com
`OwlError: Got duplicate key in t-foreach`. A causa não é o agrupamento: é o
dado. O Odoo devolve UM grupo para o `NULL` e OUTRO para a string vazia, e os
dois chegam ao `t-foreach` com a mesma chave -- vazia. Owl recusa chave
repetida, e com razão.

No prod eram 933 coleções, 946 subtítulos e 514 listas de palavra-chave
gravados como `''` pelo importador, que escrevia `or ""` onde o Odoo espera
`False`. O importador foi corrigido; isto arruma o que ele já tinha escrito.

Só normaliza vazio: nenhum texto de verdade é tocado.
"""
import logging

_logger = logging.getLogger(__name__)

COLUNAS = ('metabooks_collections', 'metabooks_book_subtitle',
           'synopsys', 'metabooks_keywords', 'metabooks_label')


def migrate(cr, version):
    for coluna in COLUNAS:
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'product_template' AND column_name = %s
        """, (coluna,))
        if not cr.fetchone():
            continue
        cr.execute("""
            UPDATE product_template
               SET %s = NULL
             WHERE %s = ''
        """ % (coluna, coluna))
        if cr.rowcount:
            _logger.info("metabooks: %s vazio(s) viraram nulo em %s",
                         cr.rowcount, coluna)
