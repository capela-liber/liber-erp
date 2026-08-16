# -*- coding: utf-8 -*-
"""O parser da conversa: texto (ou colagem de Excel) -> pares qty x título.

Funções PURAS, testáveis sem ORM (a regra do CLAUDE.md). O formato real da
caixa comercial (amostra ago/2026) é lista com um título por linha:

    3 Fim do SUS?
    2x Banguela
    Imaginações pós-capitalistas        (sem número = 1)

Colagem vinda do Excel chega separada por TAB:

    Fim do SUS?\t3
    9788577151234\t2
"""
import html as _html
import re

# 13 dígitos começando por 978/979 = ISBN-13 (o barcode dos livros)
ISBN_RE = re.compile(r'\b(97[89]\d{10})\b')

# "3 Título", "3x Título", "03 - Título"
QTY_FIRST_RE = re.compile(r'^\s*(\d{1,4})\s*(?:x|X|un\.?|-|—)?\s+(\S.*)$')
# "Título<TAB>3", "Título ; 3", "Título - 3" (fim da linha)
QTY_LAST_RE = re.compile(r'^(\S.*?)\s*[;\t]\s*(\d{1,4})\s*$')

# linhas que são conversa, não item — saudação, endereço, assinatura,
# telefone (o "11 98883-0332" da assinatura NÃO é 11 exemplares)
NOISE_RE = re.compile(
    r'^(oi|olá|ola|bom dia|boa tarde|boa noite|att|abs|abraço|abracao|'
    r'obrigad|valeu|segue|prezad|cordialmente|atenciosamente)|'
    r'(cep\s*[\d.-]|rua |av\.|avenida |aos cuidados|whatsapp|'
    r'enviado por|mantido por|\b\d{4,5}-\d{4}\b)', re.IGNORECASE)


# quebras de bloco viram \n ANTES de remover as tags — o html2plaintext do
# Odoo colapsa <div>s numa linha só, e um parser por linha fica cego
TAG_BREAK_RE = re.compile(r'(?i)<\s*br\s*/?\s*>|</\s*(div|p|li|tr|h\d)\s*>')
TAG_RE = re.compile(r'<[^>]+>')


def html_to_text(src):
    """HTML de e-mail -> texto com uma linha por bloco. Pura."""
    if not src:
        return ''
    text = TAG_BREAK_RE.sub('\n', src)
    text = TAG_RE.sub('', text)
    return _html.unescape(text).replace('\xa0', ' ')


TABLE_FRAG_RE = re.compile(r'(?is)<table.*?</table>')
TR_RE = re.compile(r'(?is)<tr.*?</tr>')
CELL_RE = re.compile(r'(?is)<t[dh][^>]*>(.*?)</t[dh]>')


def _cell_text(raw):
    return re.sub(r'\s+', ' ',
                  _html.unescape(TAG_RE.sub('', raw))).strip()


def _digits(text):
    return re.sub(r'\D', '', text or '')


def table_items(rows):
    """Linhas de células -> itens {'qty','label','isbn'}.

    UMA regra, burra de propósito (pedido do usuário, 10/08): **achou
    ISBN + número na linha, o número é a quantidade** — o primeiro número
    puro depois do título; sem número, 1. Nada de interpretar cabeçalho
    nem calcular mínimo − estoque: inferência é assunto para o módulo
    claude, depois. Linha de tabela sem ISBN não vira item.
    """
    items = []
    for row in rows:
        isbn = None
        isbn_idx = None
        for i, cell in enumerate(row):
            code = _digits(cell)
            if re.fullmatch(r'97[89]\d{10}', code):
                isbn, isbn_idx = code, i
                break
        if not isbn:
            continue
        rest = [c for i, c in enumerate(row) if i != isbn_idx]
        label = next((c for c in rest
                      if c.strip() and not re.fullmatch(
                          r'[\d\s.,-]+', c)), '')
        nums = [int(c.strip()) for c in rest
                if re.fullmatch(r'\d{1,4}', c.strip())]
        items.append({'qty': nums[0] if nums else 1,
                      'label': label or isbn, 'isbn': isbn})
    return items


def extract_report_tables(html):
    """HTML -> (html sem as tabelas-relatório, itens delas).

    Só remove do texto a tabela que RENDEU itens — tabela de layout fica,
    e o texto em volta continua indo para o parser de linhas."""
    items = []
    out = html or ''
    for frag in TABLE_FRAG_RE.findall(out):
        rows = [[_cell_text(c) for c in CELL_RE.findall(tr)]
                for tr in TR_RE.findall(frag)]
        got = table_items([r for r in rows if r])
        if got:
            items.extend(got)
            out = out.replace(frag, '\n')
    return out, items


def items_to_text(items):
    """Itens -> linhas TSV 'label<TAB>isbn<TAB>qty' que o parse_lines
    relê — assim o rascunho continua sendo texto, editável."""
    return '\n'.join(
        f"{it['label']}\t{it['isbn'] or ''}\t{it['qty']}"
        for it in items)


def parse_lines(text):
    """Extrai candidatos (qty, texto_do_título, isbn_ou_None) de um texto.

    Devolve lista de dicts {'qty', 'label', 'isbn'}. Linha sem número vira
    qty=1 SÓ quando parece título (curta, sem cara de frase de conversa).
    """
    out = []
    for raw in (text or '').splitlines():
        line = raw.strip().strip('*').strip()
        if not line or NOISE_RE.search(line):
            continue
        isbn = None
        m_isbn = ISBN_RE.search(line)
        if m_isbn:
            isbn = m_isbn.group(1)
            line_wo = ISBN_RE.sub('', line).strip(' \t-;')
        else:
            line_wo = line
        if isbn:
            # a regra: achou ISBN + número, o número é a quantidade —
            # e este ramo vem ANTES dos genéricos, senão o QTY_LAST pega
            # o desconto no fim da linha da planilha (o 40 do modelo de
            # importação, caso HD/143298). Divide em células: primeiro
            # número PURO é a quantidade, primeira célula com letras é o
            # rótulo.
            cells = [c.strip() for c in re.split(r'[\t;]', line_wo)
                     if c.strip()]
            qty = next((int(c) for c in cells
                        if re.fullmatch(r'\d{1,4}', c)), None)
            if qty is None:
                # texto corrido: "2 exemplares do <isbn>"
                m = QTY_FIRST_RE.match(line_wo)
                qty = int(m.group(1)) if m else 1
            label = next((c for c in cells
                          if re.search(r'[^\W\d_]', c)), '') or isbn
            out.append({'qty': qty, 'label': label, 'isbn': isbn})
            continue
        m = QTY_FIRST_RE.match(line_wo)
        if m:
            out.append({'qty': int(m.group(1)),
                        'label': m.group(2).strip(), 'isbn': None})
            continue
        m = QTY_LAST_RE.match(line_wo)
        if m:
            out.append({'qty': int(m.group(2)),
                        'label': m.group(1).strip(), 'isbn': None})
            continue
        # linha sem número: título avulso se tiver 2+ palavras (uma palavra
        # só é indistinguível de assinatura — "Caio") e não terminar em
        # pontuação de frase
        if 3 <= len(line_wo) <= 80 and not line_wo.endswith(('?', '!', ':')) \
                and 2 <= len(line_wo.split()) <= 10:
            out.append({'qty': 1, 'label': line_wo, 'isbn': None})
    return out


def xlsx_rows_to_text(rows):
    """Linhas de células (listas) -> texto TAB-separado para o parse_lines.
    Pura: recebe listas já lidas, não abre arquivo. O openpyxl entrega
    número como float — 9786589705468.0 NÃO é um ISBN e 40.0 não é 40;
    float inteiro vira inteiro antes de virar texto."""
    lines = []
    for row in rows:
        cells = []
        for c in row:
            if c in (None, ''):
                continue
            if isinstance(c, float) and c.is_integer():
                c = int(c)
            cells.append(str(c).strip())
        if cells:
            lines.append('\t'.join(cells))
    return '\n'.join(lines)
