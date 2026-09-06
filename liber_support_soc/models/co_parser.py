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

# 13 dígitos começando por 978/979 = ISBN-13 (o barcode dos livros).
# Aceita a pontuação humana no meio ("978-85-7715-123-4"), que a planilha
# da livraria traz com frequência — os separadores caem no _digits.
ISBN_RE = re.compile(
    r'(?<!\d)(97[89][\d\u2010-\u2015 .\u00b7-]{9,18}\d)(?!\d)')


def find_isbn(text):
    """Primeiro ISBN-13 do texto -> (isbn_só_dígitos, início, fim), ou
    (None, -1, -1). O candidato do ISBN_RE vem largo de propósito (a
    pontuação humana entra) e é aqui que se exige EXATAMENTE 13 dígitos —
    senão o '.0' que o Excel gruda no número entraria no código."""
    for m in ISBN_RE.finditer(text or ''):
        code = _digits(m.group(1))
        if len(code) == 13:
            return code, m.start(1), m.end(1)
        # o candidato pode ter engolido lixo à direita ('9786589705468.0');
        # tenta de novo só com o prefixo de 13 dígitos
        if len(code) > 13:
            seen = 0
            for i, ch in enumerate(m.group(1)):
                if ch.isdigit():
                    seen += 1
                    if seen == 13:
                        return (code[:13], m.start(1),
                                m.start(1) + i + 1)
    return None, -1, -1

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
        if not line:
            continue
        isbn, start, end = find_isbn(line)
        if isbn:
            line_wo = (line[:start] + ' ' + line[end:]).strip(' \t-;')
        else:
            line_wo = line
        # o filtro de conversa não manda em linha que traz ISBN: a linha
        # do produto da planilha do FNDE carrega o endereço do órgão
        # ("CEP 70070-929") e ia embora inteira (arquivo 97431.xlsx)
        if not isbn and NOISE_RE.search(line):
            continue
        if is_header_row(re.split(r'[\t;]', line_wo)):
            continue
        # formato canônico 'rótulo<TAB>isbn<TAB>quantidade' — o que o
        # items_to_text e o rows_to_text emitem. Aqui a posição já é
        # sabida e não se adivinha: sem isso um rótulo numérico (a coluna
        # 'Item' com 0001) era relido como se fosse a quantidade.
        parts = raw.split('\t')
        if isbn and len(parts) == 3 and _digits(parts[1]) == isbn:
            qty = _qty_from(parts[2])
            out.append({'qty': 1 if qty is None else qty,
                        'label': parts[0].strip() or isbn, 'isbn': isbn})
            continue
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


# ---------------------------------------------------------------------
# NFe XML: a melhor fonte de todas — ISBN (cEAN) e quantidade (qCom)
# exatos, sem fuzzy. O desenho espelha o liber_nfe_xml, mas em funções
# puras: bytes entram, itens saem, nada de ORM.
# ---------------------------------------------------------------------

NFE_NS = '{http://www.portalfiscal.inf.br/nfe}'


def _nfe_root(raw):
    """bytes -> ElementTree root, ou None se não for XML são."""
    import xml.etree.ElementTree as ET
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return None


def is_nfe_xml(name, raw):
    """É um XML de NFe? Pelo nome OU pelo conteúdo — o anexo do e-mail
    às vezes chega como '35240812345....xml', às vezes 'nota (3).XML'."""
    if not raw:
        return False
    head = raw[:512]
    if b'infNFe' in raw[:4096] or b'portalfiscal.inf.br/nfe' in raw[:4096]:
        return True
    return (name or '').lower().endswith('.xml') and (
        head.lstrip()[:5] in (b'<?xml', b'<nfeP', b'<NFe ', b'<NFe>'))


def nfe_items(raw):
    """NFe XML (bytes) -> itens {'qty', 'label', 'isbn'}.

    Um item por <det>: rótulo do xProd, quantidade do qCom (float da
    SEFAZ, '3.0000' é 3), ISBN do cEAN quando é ISBN-13 de verdade —
    'SEM GTIN' e códigos internos não viram isbn. XML quebrado devolve
    lista vazia, não exceção: quem chama decide o fallback."""
    root = _nfe_root(raw)
    if root is None:
        return []
    items = []
    for det in root.findall('.//%sdet' % NFE_NS):
        label_node = det.find('.//%sxProd' % NFE_NS)
        qty_node = det.find('.//%sqCom' % NFE_NS)
        isbn = None
        for tag in ('cEAN', 'cProd'):
            node = det.find('.//%s%s' % (NFE_NS, tag))
            code = _digits(node.text if node is not None else '')
            if re.fullmatch(r'97[89]\d{10}', code):
                isbn = code
                break
        try:
            qty = int(float(qty_node.text)) if qty_node is not None else 1
        except (TypeError, ValueError):
            qty = 1
        label = (label_node.text or '').strip() if label_node is not None \
            else ''
        if not (label or isbn):
            continue
        items.append({'qty': qty or 1, 'label': label or isbn,
                      'isbn': isbn})
    return items


def nfe_party_docs(raw):
    """NFe XML (bytes) -> conjunto de CNPJs/CPFs (só dígitos) das DUAS
    pontas, emitente e destinatário. Numa devolução a livraria é a
    EMITENTE — ler só o primeiro <CNPJ> já nos custou uma volta no
    liber_nfe_xml, daí o conjunto."""
    root = _nfe_root(raw)
    if root is None:
        return set()
    docs = set()
    for tag in ('emit', 'dest'):
        node = root.find('.//%s%s' % (NFE_NS, tag))
        if node is None:
            continue
        doc = node.find('.//%sCNPJ' % NFE_NS)
        if doc is None:
            doc = node.find('.//%sCPF' % NFE_NS)
        if doc is not None and doc.text:
            docs.add(_digits(doc.text))
    return docs - {''}


# ---------------------------------------------------------------------
# Planilhas: o que a caixa comercial realmente recebe
#
# Censo de 01/09/2026 sobre os 84 anexos de planilha dos chamados (banco
# dev): 61% eram .xls OLE do Excel antigo, 17% eram SpreadsheetML (ou
# HTML) com a extensão .xls, e só 23% eram .xlsx de verdade. Ler pela
# EXTENSÃO não serve; quem manda é a assinatura do arquivo.
# ---------------------------------------------------------------------

# vocabulário de cabeçalho. Sem acento e em minúscula (ver _norm_head).
# 'estoque' e 'consignado' NÃO são quantidade — foi a coluna 'estoque'
# valendo 0 que fez o arquivo 97202.xlsx importar zero em tudo.
HEAD_QTY = ('quantidade', 'qtde', 'qtd', 'qte', 'sugestao', 'exemplares',
            'unidades', 'volumes', 'pedido', 'a enviar', 'solicitado')
HEAD_ISBN = ('isbn', 'ean', 'gtin', 'codigo de barras', 'cod de barras',
             'cod barras', 'barcode', 'cod. barras')
HEAD_LABEL = ('titulo', 'produto', 'obra', 'livro', 'descricao', 'item',
              'nome', 'nome item', 'material')

_ACCENTS = str.maketrans('áàâãäéèêëíìîïóòôõöúùûüçñ',
                         'aaaaaeeeeiiiiooooouuuucn')


def _norm_head(cell):
    """Célula de cabeçalho -> chave comparável: sem acento, sem
    pontuação de borda, minúscula, espaço colapsado."""
    text = re.sub(r'\s+', ' ', str(cell or '')).strip().lower()
    return text.translate(_ACCENTS).strip(' .:*#()')


def _head_kind(cell):
    """Que coluna esse cabeçalho anuncia? 'qty', 'isbn', 'label' ou None.

    Casa por igualdade ou por palavra de borda — 'Qtde.' e 'Cód. Barras'
    contam, 'Quantidade em estoque' não vira qty por acidente porque
    'estoque' fica fora do vocabulário."""
    kind, _rank = _head_kind_rank(cell)
    return kind


def _head_kind_rank(cell):
    """(tipo, preferência) do cabeçalho. A preferência é a posição da
    palavra no vocabulário, e é ela que decide quando a mesma planilha
    traz duas colunas do mesmo tipo: 'Título' ganha de 'Item' como
    rótulo, senão o rótulo vira o número de sequência da linha (a coluna
    'Item' com 0001, 0002... do arquivo 97607.xls)."""
    key = _norm_head(cell)
    if not key or len(key) > 40:
        return None, 99
    for kind, words in (('qty', HEAD_QTY), ('isbn', HEAD_ISBN),
                        ('label', HEAD_LABEL)):
        for rank, word in enumerate(words):
            if key == word or key.startswith(word + ' ') \
                    or key.endswith(' ' + word):
                return kind, rank
    return None, 99


def is_header_row(cells):
    """A linha é um cabeçalho de tabela (e não um item)?

    Exige duas colunas reconhecidas e nenhum ISBN de verdade na linha —
    'ISBN 9788577151234' numa linha de dado não pode virar cabeçalho."""
    cells = [str(c or '') for c in cells]
    if any(re.fullmatch(r'97[89]\d{10}', _digits(c)) for c in cells):
        return False
    kinds = {k for k in (_head_kind(c) for c in cells) if k}
    return len(kinds) >= 2


def header_map(rows, look=25):
    """Acha a linha de cabeçalho e o que cada coluna significa.

    Devolve (índice_da_linha, {'qty': i, 'isbn': i, 'label': i}) ou
    (None, {}). Procura nas primeiras `look` linhas porque a planilha da
    livraria abre com título de relatório, empresa, contrato — o
    cabeçalho real do 22174.xlsx está na sétima linha.

    Havendo mais de uma coluna do mesmo tipo, vale a PRIMEIRA: em
    'ean | produto | estoque | consignado | sugestao' só 'sugestao' é
    quantidade, e em 'Título | Cód. Barras' o rótulo é o título."""
    winner = None
    for idx, row in enumerate(rows[:look]):
        if not is_header_row(row):
            continue
        best = {}
        hits = 0
        for i, cell in enumerate(row):
            kind, rank = _head_kind_rank(cell)
            if not kind:
                continue
            hits += 1
            if rank < best.get(kind, (99, 0))[0]:
                best[kind] = (rank, i)
        cols = {k: i for k, (_r, i) in best.items()}
        if 'isbn' not in cols and 'label' not in cols:
            continue
        # a MELHOR candidata, não a primeira: o cabeçalho da empresa
        # ("Pedido de Consignação Nº 5.802" ... "isbn correto") casa duas
        # palavras e vinha antes do cabeçalho real da tabela, que casa
        # quatro (arquivo 96315.xls)
        score = (len(cols), hits)
        if winner is None or score > winner[0]:
            winner = (score, idx, cols)
    if winner is None:
        return None, {}
    return winner[1], winner[2]


def _cell_str(value):
    """Célula de planilha -> texto. O openpyxl entrega número como float
    e 9786589705468.0 não é um ISBN; float inteiro vira inteiro."""
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _qty_from(text):
    """Texto de célula -> quantidade inteira, ou None se não for número.
    '2', '2.0' e '2,00' são 2; '' e 'a combinar' não são quantidade."""
    text = (text or '').strip().replace(',', '.')
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if value < 0 or value > 999999:
        return None
    return int(value)


def rows_to_text(rows):
    """Linhas de planilha -> texto para o parse_lines.

    Com cabeçalho reconhecido, emite o TSV canônico 'label\tisbn\tqty'
    lendo cada valor da SUA coluna — é o que impede a coluna de estoque,
    de preço ou de desconto de virar quantidade. Sem cabeçalho, cai no
    comportamento antigo (a regra posicional do xlsx_rows_to_text)."""
    rows = [list(r) for r in rows]
    head_idx, cols = header_map(rows)
    if head_idx is None:
        def tem_isbn(row):
            return any(re.fullmatch(r'97[89]\d{10}', _digits(_cell_str(c)))
                       for c in row)
        # sem cabeçalho reconhecido, a planilha COMPRIDA (ou a que já
        # mostra ISBN em alguma linha) só rende item onde há ISBN: é a
        # doutrina do table_items, e sem ela um relatório vira uma grade
        # de 'PÁG.: 1' e 'DADOS GERAIS'. A lista curta colada à mão
        # ('Título do Rascunho;3') não tem ISBN nem deixa de valer
        if len(rows) > 5 or any(tem_isbn(r) for r in rows):
            rows = [r for r in rows if tem_isbn(r)]
        return xlsx_rows_to_text(rows)
    lines = []
    for row in rows[head_idx + 1:]:
        cells = [_cell_str(c) for c in row]

        def at(kind):
            i = cols.get(kind)
            return cells[i] if i is not None and i < len(cells) else ''

        isbn = _digits(at('isbn'))
        if not re.fullmatch(r'97[89]\d{10}', isbn):
            isbn = ''
        label = at('label')
        if not label:
            # cabeçalho com célula mesclada não fica sobre a sua coluna:
            # no relatório da distribuidora o 'Produto' está na coluna 3 e
            # o título na 1. Sem valor na coluna anunciada, vale a
            # primeira célula com letras que não seja o ISBN
            label = next((c for i, c in enumerate(cells)
                          if i != cols.get('isbn')
                          and re.search(r'[^\W\d_]', c)), '')
        if not (label or isbn):
            continue
        # sem coluna de quantidade (lista de preços, catálogo), o item
        # vale 1 — melhor que deixar a regra posicional eleger o número
        # de páginas ou o preço como quantidade
        qty = _qty_from(at('qty')) if 'qty' in cols else None
        lines.append('%s\t%s\t%s' % (label, isbn, 1 if qty is None else qty))
    return '\n'.join(lines)


SPREADSHEETML_NS = '{urn:schemas-microsoft-com:office:spreadsheet}'


def is_spreadsheetml(raw):
    """XML do Excel 2003 (SpreadsheetML)? Vem com extensão .xls e
    enganava o leitor, que o tratava como texto solto."""
    head = (raw or b'')[:2048]
    return (b'urn:schemas-microsoft-com:office:spreadsheet' in head
            or b'progid="Excel.Sheet"' in head)


def spreadsheetml_rows(raw):
    """SpreadsheetML (bytes) -> linhas de células, de TODAS as abas.

    Respeita o ss:Index, que é como o formato representa célula pulada:
    ignorá-lo desalinha a linha e joga o valor na coluna errada."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    pages = []
    for sheet in root.iter(SPREADSHEETML_NS + 'Worksheet'):
        rows = []
        for row in sheet.iter(SPREADSHEETML_NS + 'Row'):
            rows.append(_spreadsheetml_cells(row))
        pages.append(rows)
    return pages


def _spreadsheetml_cells(row):
    """Uma <Row> -> lista de células, respeitando o ss:Index."""
    cells = []
    for cell in row.findall(SPREADSHEETML_NS + 'Cell'):
        index = cell.get(SPREADSHEETML_NS + 'Index')
        if index:
            try:
                cells.extend([''] * (int(index) - 1 - len(cells)))
            except ValueError:
                pass
        data = cell.find(SPREADSHEETML_NS + 'Data')
        cells.append(_cell_text(
            ''.join(data.itertext())) if data is not None else '')
    return cells


def is_html_table(raw):
    """Relatório em HTML salvo com nome de planilha — o sistema da
    livraria exporta assim (arquivo 22351.xls)."""
    head = (raw or b'')[:2048].lstrip(b'\xef\xbb\xbf').lstrip().lower()
    return head.startswith((b'<html', b'<div', b'<table', b'<!doctype html'))


def html_table_rows(raw):
    """HTML (bytes) -> linhas de células de todas as <table>."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')
    pages = []
    for frag in TABLE_FRAG_RE.findall(text):
        rows = [cells for cells in
                ([_cell_text(c) for c in CELL_RE.findall(tr)]
                 for tr in TR_RE.findall(frag)) if cells]
        if rows:
            pages.append(rows)
    return pages


def xls_ole_rows(raw):
    """.xls OLE do Excel antigo (bytes) -> linhas de TODAS as abas.

    Era a maioria dos anexos e o único formato que estourava exceção: o
    leitor tratava o binário como texto e o csv.reader morria com
    'new-line character seen in unquoted field'."""
    import xlrd
    book = xlrd.open_workbook(file_contents=raw)
    return [[[_cell_str(c) for c in sheet.row_values(i)]
             for i in range(sheet.nrows)]
            for sheet in book.sheets()]


def xlsx_rows(raw):
    """.xlsx (bytes) -> linhas de TODAS as abas.

    Todas, e não só a primeira: a planilha-padrão de metadados abre com
    a aba '(1) Instruções de Preenchimento' e os dados moram na (2) —
    ler worksheets[0] devolvia a bula e nenhum item (92418.xlsx)."""
    import io as _io
    import openpyxl
    book = openpyxl.load_workbook(_io.BytesIO(raw), read_only=True,
                                  data_only=True)
    return [[[_cell_str(c) for c in row]
             for row in sheet.iter_rows(values_only=True)]
            for sheet in book.worksheets]


def csv_rows(raw):
    """CSV/TSV (bytes) -> linhas de células.

    O delimitador sai do Sniffer, não de `';' in text`: um ponto e
    vírgula dentro de um título fazia o arquivo inteiro, separado por
    vírgula, virar uma coluna só."""
    import csv
    import io as _io
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')
    sample = '\n'.join(text.splitlines()[:20])
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=';,\t|').delimiter
    except csv.Error:
        delimiter = ';' if sample.count(';') > sample.count(',') else ','
    return [[r for r in csv.reader(_io.StringIO(text),
                                   delimiter=delimiter)
             if any(c.strip() for c in r)]]


def sheet_pages(name, raw):
    """(nome, bytes) de qualquer planilha -> uma lista de linhas POR ABA.

    Aba a aba, e não tudo num monte: a planilha-padrão de metadados abre
    com 600 linhas de bula na aba (1) e os dados moram na (2) — junto,
    o cabeçalho da segunda fica longe demais para ser achado.

    A ordem do reconhecimento é pela ASSINATURA do arquivo, e o nome só
    desempata no fim: metade dos anexos reais chega com a extensão
    errada (.xls em arquivo que é XML, HTML ou zip)."""
    if not raw:
        return []
    if raw[:4] == b'PK\x03\x04':
        return xlsx_rows(raw)
    if raw[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        return xls_ole_rows(raw)
    if is_spreadsheetml(raw):
        return spreadsheetml_rows(raw)
    if is_html_table(raw):
        return html_table_rows(raw)
    return csv_rows(raw)


def sheet_rows(name, raw):
    """Todas as linhas de todas as abas, numa lista só."""
    return [row for page in sheet_pages(name, raw) for row in page]


def _page_is_strong(page):
    """A aba tem cabeçalho reconhecido ou ISBN? A aba fraca é a bula —
    'Preencha na aba ao lado' não é um item."""
    if header_map(page)[0] is not None:
        return True
    return any(re.fullmatch(r'97[89]\d{10}', _digits(_cell_str(c)))
               for row in page for c in row)


def sheet_to_text(name, raw):
    """(nome, bytes) de planilha -> texto para o parse_lines.

    É a porta de entrada, e cada aba resolve o seu cabeçalho por conta
    própria. Havendo aba com cabeçalho ou ISBN, as abas fracas ficam de
    fora: senão a aba de instruções entra na grade junto com o pedido."""
    pages = sheet_pages(name, raw)
    strong = [p for p in pages if _page_is_strong(p)]
    parts = [rows_to_text(page) for page in (strong or pages)]
    return '\n'.join(p for p in parts if p.strip())


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
