# -*- coding: utf-8 -*-
"""Which product.template field feeds which Metabooks column.

Kept apart from metabooks_sheet.py, which is about the file format alone, and
apart from the models, which are about reading records. This is the seam: the
one place to look when asking "do we send X?".

Deliberately partial. Of the 74 columns in the standard template we map the ones
we actually hold in Odoo; the rest are never written, so Metabooks keeps
whatever it has for them (updates are incremental -- see metabooks_sheet). Adding
a column here is what makes a field start being exported, and start marking
books dirty when edited. The two follow from one list on purpose: marking a book
dirty over a field we cannot send would be a lie to whoever reads the queue.

'kind' says how to turn the stored value into a cell, and which delete marker
clears it. The formats come from the 2025 filling guide and from the example row
in the official template:
    Autor      Silva, Augusto da; Araújo, Michele   (surname first, "; " between)
    Formato    BC                                   (ONIX list 150 code)
    Data       44545                                (a real date, Excel serial)
    NCM        4901.99.00
    Idiomas    por                                  (ISO 639-2/B)
    BISAC      LAN025030
"""

TEXT = 'text'
INT = 'int'
FLOAT = 'float'
PRICE = 'price'
DATE = 'date'
URL = 'url'
CODE = 'code'          # Selection: send the stored ONIX code, not the label
M2O_NAME = 'm2o_name'
COUNTRY = 'country'    # res.country -> ISO code
AUTHORS = 'authors'    # book_auther_ids filtered by ONIX contributor role
BISAC = 'bisac'
AVAILABILITY = 'availability'

# (odoo field, Metabooks column, kind, extra)
FIELD_MAP = (
    ('metabooks_vendor_id', 'MB ID Editor', TEXT, None),
    ('book_auther_ids', 'Autor', AUTHORS, 'A01'),
    ('book_auther_ids', 'Organizador', AUTHORS, 'B01'),
    ('book_auther_ids', 'Tradutor', AUTHORS, 'B06'),
    ('book_auther_ids', 'Ilustrador', AUTHORS, 'A12'),
    ('metabooks_book_title', 'Título', TEXT, None),
    ('metabooks_book_subtitle', 'Subtítulo', TEXT, None),
    ('metabooks_language', 'Idiomas do produto', TEXT, None),
    ('metabooks_original_language', 'Traduzido de', TEXT, None),
    ('metabooks_product_form', 'Formato', CODE, None),
    ('metabooks_binding', 'Acabamento', CODE, None),
    ('metabooks_height', 'Altura', FLOAT, None),
    ('metabooks_width', 'Largura', FLOAT, None),
    ('metabooks_thickness', 'Profundidade', FLOAT, None),
    ('metabooks_weight', 'Peso', FLOAT, None),
    ('metabooks_publish_date', 'Data de publicação', DATE, None),
    ('metabooks_product_availability', 'Status de disponibilidade',
     AVAILABILITY, None),
    ('metabooks_edition_type', 'Tipo de edição', TEXT, None),
    ('metabooks_edition_number', 'Número da edição', INT, None),
    ('metabooks_page_count', 'Número de páginas', INT, None),
    ('metabooks_illustration_count', 'Ilustrações', INT, None),
    ('metabooks_collections', 'Série', TEXT, None),
    ('metabooks_publication_city', 'Local de publicação', TEXT, None),
    ('metabooks_publication_country', 'País de publicação', COUNTRY, None),
    ('metabooks_ncm', 'NCM', TEXT, None),
    ('metabooks_country_of_manufacture', 'País de origem', COUNTRY, None),
    ('metabooks_keywords', 'Palavra-chave', TEXT, None),
    ('bisac_code_ids', 'BISAC', BISAC, None),
    ('synopsys', 'Sinopse', TEXT, None),
    ('list_price', 'R$', PRICE, None),
    ('metabooks_image_url', 'Capa', URL, None),
)

# Fields whose edit marks a book as pending export. Exactly the mapped ones.
WATCHED_FIELDS = frozenset(field for field, _c, _k, _e in FIELD_MAP)

# One column can be fed by more than one field (four contributor roles all read
# book_auther_ids), so index by column rather than the other way round.
BY_COLUMN = {column: (field, kind, extra)
             for field, column, kind, extra in FIELD_MAP}


def columns_for(field):
    """Columns a given Odoo field feeds."""
    return [column for f, column, _k, _e in FIELD_MAP if f == field]
