# -*- coding: utf-8 -*-
"""O relatório mensal da Bookwire -> linhas de pedido de venda.

Lógica pura, sem ORM: lê, agrupa e fecha a conta ao centavo.

A Bookwire manda, por empresa e por mês, um e-mail "Sales Report" com um ZIP:
o PDF do relatório, uma nota de crédito e um **CSV nativo** (`;`, UTF-8 com
BOM, vírgula decimal). O CSV é a fonte: uma linha por venda, com loja, país,
formato (EPUB, Audiobook, Audiotrack), tipo (`sale`/`retour`), unidades e o
líquido da editora ("Payment Amount Publisher"). O xlsx que circulava na casa
era conversão do PDF feita à mão -- não serve.

Três decisões moram aqui:

- **Uma linha por título**, com as unidades líquidas (venda menos devolução).
  O pedido é o que a casa vendeu à Bookwire no mês; loja e país ficam no
  relatório.
- **Audiotrack é 1 unidade.** São faixas de audiolivro em streaming: 287
  faixas somaram R$ 1,41 em junho/2026. Contá-las como exemplares faria o
  relatório de vendas dizer 517 onde a casa vendeu ~240.
- **O total fecha ao centavo.** O Odoo guarda o preço unitário com 2 casas;
  R$ 0,39 por 62 unidades não tem preço unitário exato. Quando a divisão não
  fecha, o título vira duas linhas: N-1 unidades ao preço arredondado para
  baixo e 1 unidade com o resto. O pedido soma exatamente o que a Bookwire
  paga -- e é esse valor que a nota vai declarar.
"""
import csv
import io
import re
import zipfile

#: Colunas sem as quais o arquivo não é o relatório da Bookwire.
ASSINATURA = ('ISBN', 'Format', 'Sale Type', 'Units',
              'Payment Amount Publisher')

FAIXA = 'audiotrack'


def _texto(raw):
    for enc in ('utf-8-sig', 'latin-1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ''


def _eh_relatorio(texto):
    cabecalho = texto.lstrip().split('\n', 1)[0]
    return all('"%s"' % c in cabecalho or c in cabecalho.split(';')
               for c in ASSINATURA)


def ler(nome, raw):
    """O texto do CSV da Bookwire em `raw` (CSV solto ou dentro de ZIP),
    ou None se não houver relatório ali."""
    raw = raw or b''
    if raw[:2] == b'PK':
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            return None
        for info in zf.infolist():
            if info.filename.lower().endswith('.csv'):
                texto = _texto(zf.read(info))
                if _eh_relatorio(texto):
                    return texto
        return None
    if not (nome or '').lower().endswith('.csv'):
        return None
    texto = _texto(raw)
    return texto if _eh_relatorio(texto) else None


def _numero(valor):
    """'1.234,56' -> 1234.56; '0,0096235300' -> 0.00962353."""
    valor = (valor or '').strip()
    if not valor:
        return 0.0
    return float(valor.replace('.', '').replace(',', '.'))


def _centavos(valor):
    return int(round(_numero(valor) * 100))


def interpretar(texto):
    """{'editora', 'periodo' ('MM/AAAA'), 'titulos': [...]} do CSV.

    Cada título: isbn, titulo, faixa (bool), formatos, unidades (líquidas) e
    centavos (líquido da editora, em centavos, para somar sem erro de float).
    """
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=';'))
    if not linhas:
        raise ValueError('relatório da Bookwire sem nenhuma linha')
    grupos = {}
    for linha in linhas:
        isbn = re.sub(r'\D', '', linha.get('ISBN') or '')
        formato = (linha.get('Format') or '').strip()
        faixa = formato.lower() == FAIXA
        g = grupos.setdefault((isbn, faixa), {
            'isbn': isbn, 'titulo': (linha.get('Title') or '').strip(),
            'faixa': faixa, 'formatos': set(), 'unidades': 0, 'centavos': 0,
        })
        g['formatos'].add(formato)
        # A devolução chega como linha própria, com unidades e valor já
        # negativos: somar é o que a torna líquida.
        g['unidades'] += int(round(_numero(linha.get('Units'))))
        g['centavos'] += _centavos(linha.get('Payment Amount Publisher'))
    inicio = (linhas[0].get('Period Start Date') or '').strip()   # 01.06.2026
    partes = inicio.split('.')
    return {
        'editora': (linhas[0].get('Publisher') or '').strip(),
        'periodo': ('%s/%s' % (partes[1], partes[2])
                    if len(partes) == 3 else ''),
        'titulos': list(grupos.values()),
    }


def linhas_do_pedido(titulos):
    """Os títulos viram linhas de pedido (isbn, titulo, qty, preco, nota)
    cuja soma é, ao centavo, o líquido do relatório."""
    saida = []
    for t in titulos:
        base = {'isbn': t['isbn'], 'titulo': t['titulo']}
        qty, cents = t['unidades'], t['centavos']
        if t['faixa']:
            if cents:
                saida.append(dict(base, qty=1, preco=cents / 100.0,
                                  nota='Audiotrack: %d faixa(s)' % qty))
            continue
        if qty <= 0:
            # Devolução que zerou o título: sem unidade, sem valor, sem linha.
            # Com valor (devolução a preço de outro mês), vai como ajuste.
            if cents:
                saida.append(dict(base, qty=1, preco=cents / 100.0,
                                  nota='Ajuste: %d unidade(s) líquida(s)' % qty))
            continue
        preco = cents // qty      # para baixo: o resto nunca fica negativo
        if preco * qty == cents:
            saida.append(dict(base, qty=qty, preco=preco / 100.0, nota=''))
        else:
            saida.append(dict(base, qty=qty - 1, preco=preco / 100.0, nota=''))
            saida.append(dict(base, qty=1,
                              preco=(cents - preco * (qty - 1)) / 100.0,
                              nota=''))
    return saida
