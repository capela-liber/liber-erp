# -*- coding: utf-8 -*-
"""The title spreadsheet Metabooks accepts, and how to write one.

No Odoo import here on purpose: the layout of this file is a fact about the
Metabooks platform, not about our data model, so it stays readable and testable
on its own. models/metabooks_export.py reads products and hands rows over.

Source of truth, versioned under docs/ so we do not depend on their site:
  Metabooks_Modelo-Padrao_2025.xlsx                  (74 columns, headers below)
  Metabooks_Modelo-Padrao_Campos-Obrigatorios_2025.xlsx (the 19 required ones)
  Orientacoes_preenchimento_planilha-Metabooks_2025-1.pdf

Two rules from that documentation shape everything here:

1. An update is incremental. "Conteúdos e/ou campos não serão apagados, desde
   que não estejam contidos na tabela de Excel." So a sheet carrying only GTIN
   plus the columns that changed is safe -- it never blanks the rest. That is
   why we send a diff and not a full record, and why unused columns are dropped
   from the file entirely (the documentation allows deleting them; the header,
   not the position, identifies a column).

2. Clearing a field is therefore explicit, via a marker: DELETE_TEXT for text
   and codes, DELETE_NUMBER for numbers and prices, DELETE_DATE for dates.
"""

import io
import re
import unicodedata

import xlsxwriter

# --------------------------------------------------------------------------- #
#  Columns
# --------------------------------------------------------------------------- #

# Header row of Metabooks_Modelo-Padrao_2025.xlsx, in file order. Headers must
# match literally -- "os cabeçalhos de coluna devem ser obrigatoriamente
# definidos conforme abaixo".
COLUMNS = (
    'GTIN', 'Número de pedido', 'MB ID Editor', 'MB ID Co-Editor', 'Autor',
    'Autor ISNI', 'Editor', 'Organizador', 'Traduzido de', 'Tradutor',
    'Ilustrador', 'Título', 'Subtítulo', 'Idiomas do produto', 'Formato',
    'Acabamento', 'Suporte', 'Altura', 'Largura', 'Profundidade', 'Peso',
    'Data de publicação', 'Primeiro dia de vendas',
    'Primeira data possível do anúncio', 'Status de disponibilidade',
    'Tipo de edição', 'Número da edição', 'Texto da edição',
    'Número de páginas', 'Número (romano)', 'DRM', 'Tamanho do arquivo',
    'Países com direitos exclusivos', 'Países com direitos não-exclusivos',
    'Países sem direitos de venda', 'Regiões com direitos exclusivos',
    'Regiões com direitos não-exclusivos', 'Regiões sem direitos de venda',
    'Ilustrações', 'Tempo de execução', 'Série', 'Volume',
    'Local de publicação', 'País de publicação', 'NCM', 'País de origem',
    'Palavra-chave', 'DOI', 'BISAC', 'Categoria Thema', 'Qualificador Thema',
    'Nível educacional', 'Sinopse', 'Biografia', 'Revisão', 'Alerta de venda',
    'R$', 'Preço futuro R$', 'Data inicial do preço futuro',
    'Preço especial R$', 'Descrição do preço especial', 'Link de vídeo 1',
    'Link de vídeo 2', 'Link de vídeo 3', 'Capa',
    'Referência de produto 1 ISBN13', 'Referência de produto 1 Tipo',
    'Referência de produto 1 Tipo de produto',
    'Referência de produto 2 ISBN13', 'Referência de produto 2 Tipo',
    'Referência de produto 2 Tipo de produto',
    'Referência de produto 3 ISBN13', 'Referência de produto 3 Tipo',
    'Referência de produto 3 Tipo de produto',
)

# Metabooks_Modelo-Padrao_Campos-Obrigatorios_2025.xlsx. Required to register a
# new title (task Z); an update (task V) needs only GTIN plus what changed.
MANDATORY = (
    'GTIN', 'MB ID Editor', 'Autor', 'Título', 'Idiomas do produto', 'Formato',
    'Altura', 'Largura', 'Profundidade', 'Peso', 'Data de publicação',
    'Status de disponibilidade', 'Número da edição', 'Número de páginas',
    'NCM', 'BISAC', 'Sinopse', 'R$', 'Capa',
)

# The key Metabooks dedupes on. Always written, never counted as a change.
KEY_COLUMN = 'GTIN'

# --------------------------------------------------------------------------- #
#  Tasks and delete markers
# --------------------------------------------------------------------------- #

# First character of the file name. The Portuguese help page still shows a
# legacy 'A' example; the 2025 filling guide corrects it to V, and 'A' means
# something else entirely on the German VLB. Follow the 2025 guide.
TASK_NEW = 'Z'
TASK_UPDATE = 'V'
TASK_ARCHIVE = 'X'
TASK_REACTIVATE = 'R'

TASKS = {
    TASK_NEW: 'Cadastro novo',
    TASK_UPDATE: 'Alteração',
    TASK_ARCHIVE: 'Arquivamento',
    TASK_REACTIVATE: 'Reativação',
}

# Archiving and reactivating carry the ISBN and nothing else: "Outros campos
# não são permitidos."
KEY_ONLY_TASKS = (TASK_ARCHIVE, TASK_REACTIVATE)

DELETE_TEXT = '$$'
DELETE_NUMBER = -1
# A literal string, not a date: 1111 predates Excel's epoch and cannot be
# written as one.
DELETE_DATE = '11/11/1111'


def build_filename(task, mb_id, day, text='Alteracoes', extension='xlsx'):
    """[tarefa]_[MB ID]_[AAAAMMDD]_[texto livre].xlsx

    Example from the 2025 guide: Z_BR5108985_20250320_NovosTitulos.xls
    The free text carries no meaning for them, but it is what a human reads in
    the FTP folder, so it is worth keeping legible. Underscore is the separator,
    so it cannot appear inside the parts.
    """
    if task not in TASKS:
        raise ValueError("Unknown Metabooks task code: %r" % (task,))
    return '%s_%s_%s_%s.%s' % (
        task, _slug(mb_id), day.strftime('%Y%m%d'), _slug(text) or 'Export',
        extension)


def _slug(value):
    """ASCII, no spaces, no underscores -- the file name separator."""
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = text.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^A-Za-z0-9-]+', '', text)


# --------------------------------------------------------------------------- #
#  Writing
# --------------------------------------------------------------------------- #


def write_workbook(rows, all_columns=False):
    """Build the .xlsx and return its bytes.

    rows is a list of dicts:
        {'values': {header: value, ...}, 'changed': {header, ...}}

    Changed cells are painted red. Everything else -- the GTIN, and any column
    carried purely so a human can recognise the row -- stays black, so the file
    doubles as the review document: what is red is what we are asking Metabooks
    to alter.

    By default only columns actually carrying a value are written, which is what
    makes a diff sheet readable instead of 74 columns of blank. Pass
    all_columns=True to emit the full template layout.
    """
    used = _columns_in_use(rows) if not all_columns else list(COLUMNS)

    output = io.BytesIO()
    book = xlsxwriter.Workbook(output, {
        'in_memory': True,
        # Metabooks reads one row per title; nothing here is a formula.
        'strings_to_formulas': False,
        'strings_to_urls': False,
    })
    sheet = book.add_worksheet('Planilha1')

    header_fmt = book.add_format({
        'bold': True, 'size': 10, 'bg_color': '#DDDDDD', 'border': 1,
        'text_wrap': True, 'valign': 'vcenter',
    })
    plain = book.add_format({'size': 10, 'valign': 'top'})
    changed = book.add_format({
        'size': 10, 'valign': 'top', 'font_color': '#B00020',
        'bold': True, 'bg_color': '#FCE8E8',
    })
    date_plain = book.add_format({'size': 10, 'num_format': 'dd/mm/yyyy'})
    date_changed = book.add_format({
        'size': 10, 'num_format': 'dd/mm/yyyy', 'font_color': '#B00020',
        'bold': True, 'bg_color': '#FCE8E8',
    })

    sheet.set_row(0, 30)
    sheet.freeze_panes(1, 1)
    for col, header in enumerate(used):
        sheet.write_string(0, col, header, header_fmt)
        sheet.set_column(col, col, _column_width(header))

    for line, row in enumerate(rows, start=1):
        values = row.get('values') or {}
        marks = row.get('changed') or ()
        for col, header in enumerate(used):
            if header not in values:
                continue
            value = values[header]
            is_changed = header in marks
            _write_cell(
                sheet, line, col, value,
                changed if is_changed else plain,
                date_changed if is_changed else date_plain)

    book.close()
    return output.getvalue()


def _write_cell(sheet, row, col, value, fmt, date_fmt):
    """Write with the type Metabooks expects.

    Dates go in as real dates -- their own template carries 44545, an Excel
    serial, not a formatted string.
    """
    if value is None or value is False or value == '':
        return
    if hasattr(value, 'strftime'):
        sheet.write_datetime(row, col, value, date_fmt)
    elif isinstance(value, bool):
        sheet.write_string(row, col, 'Sim' if value else 'Não', fmt)
    elif isinstance(value, (int, float)):
        sheet.write_number(row, col, value, fmt)
    else:
        sheet.write_string(row, col, str(value), fmt)


def _columns_in_use(rows):
    """Template order, restricted to columns some row actually fills.

    The documentation allows dropping unused columns, and dropping them is the
    difference between a sheet a human can check and one they cannot.
    """
    seen = set()
    for row in rows:
        seen.update((row.get('values') or {}).keys())
    unknown = seen - set(COLUMNS)
    if unknown:
        raise ValueError(
            "Not a Metabooks column: %s" % ', '.join(sorted(unknown)))
    return [c for c in COLUMNS if c in seen]


def _column_width(header):
    if header in ('Sinopse', 'Biografia', 'Revisão'):
        return 60
    if header in ('Capa', 'Link de vídeo 1', 'Link de vídeo 2',
                  'Link de vídeo 3'):
        return 40
    if header in ('Título', 'Subtítulo', 'Autor', 'Série'):
        return 30
    return max(12, min(len(header) + 2, 22))
