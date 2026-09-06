"""Tira da fila da Metabooks o que nunca foi livro.

`list_price` é campo vigiado e mora em todo product.template, então o plano de
contas da casa -- os pseudo-produtos ADM0006 "(-) Impostos", ADM0033 "(-)
Aluguel" -- entrava na fila a cada preço mexido. O portão novo vive no write();
este passo limpa o que já estava marcado antes dele existir.

Só desmarca: nenhum livro perde a pendência, porque o filtro exige justamente a
ausência de ISBN-13 na faixa Bookland (978/979), no código de barras ou na
referência interna.
"""


def migrate(cr, version):
    # Espelha _metabooks_gtin(): código de barras SE houver, senão a
    # referência interna -- e não "qualquer um dos dois".
    cr.execute("""
        UPDATE product_template t
           SET metabooks_export_pending = false,
               metabooks_export_pending_since = NULL
         WHERE t.metabooks_export_pending
           AND regexp_replace(
                   COALESCE(
                       NULLIF((SELECT p.barcode FROM product_product p
                                WHERE p.product_tmpl_id = t.id
                                ORDER BY p.id LIMIT 1), ''),
                       t.default_code, ''),
                   '\\D', '', 'g') !~ '^97[89][0-9]{10}$'
    """)
