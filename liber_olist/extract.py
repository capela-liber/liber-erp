#!/usr/bin/env python3
"""Extrator read-only da API v2 do Olist/Tiny.

Baixa notas fiscais (+ XML de cada uma) e pedidos (+ bloco `ecommerce`) para
`liber_olist/_dump/`, sem escrever nada no Olist. Serve de base para decidir a
remontagem no Odoo — ver NOTES.md §6 (piloto read-first).

Uso:
    TINY_TOKEN=xxx python3 liber_olist/extract.py [--only notas|pedidos]

Retomável: pula o que já está em disco.
"""
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.tiny.com.br/api2"
TOKEN = os.environ["TINY_TOKEN"]
DATA = Path(__file__).resolve().parent / "_dump"
XMLS = DATA / "xml"

# A v2 limita por conta (~60 req/min). Um intervalo de 1.1 s deixa margem para
# outros consumidores da mesma conta (o próprio ERP, marketplaces).
DELAY = 1.1


def call(endpoint, **params):
    """POST no endpoint da v2. Devolve texto cru — nem todo endpoint dá JSON."""
    body = urllib.parse.urlencode({"token": TOKEN, "formato": "json", **params})
    req = urllib.request.Request(
        f"{API}/{endpoint}", data=body.encode(), method="POST"
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                time.sleep(DELAY)
                return r.read().decode("utf-8", "replace")
        except Exception as exc:  # rate limit ou instabilidade — recua e tenta de novo
            wait = 5 * (attempt + 1)
            print(f"  ! {endpoint}: {exc} — retry em {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"{endpoint} falhou após 5 tentativas")


def call_json(endpoint, **params):
    return json.loads(call(endpoint, **params))["retorno"]


def call_xml_nota(nota_id, tentativas=6):
    """XML de uma nota. Retorna o envelope <retorno> cru, ou None.

    Quando a v2 estrangula (limite por conta), ela responde HTTP 200 com um
    retorno de erro em vez do XML — indistinguível de "nota sem XML" se você só
    olhar o corpo. Por isso a ausência de <xml_nfe> é tratada como falha
    TEMPORÁRIA (recua e insiste), nunca como "essa nota não tem XML".
    """
    for attempt in range(tentativas):
        xml = call("nota.fiscal.obter.xml.php", id=nota_id)
        if "<xml_nfe>" in xml:
            return xml
        wait = 10 * (attempt + 1)
        print(f"  ~ nota {nota_id}: sem xml_nfe (limite?) — espera {wait}s",
              file=sys.stderr)
        time.sleep(wait)
    return None


def paginate(endpoint, list_key, item_key, **params):
    """Percorre todas as páginas de um endpoint de pesquisa da v2.

    O retorno vem como {list_key: [{item_key: {...}}, ...]} — e o plural do Tiny
    é irregular (`notas_fiscais` para `nota_fiscal`), por isso as duas chaves.
    """
    page, total = 1, 1
    while page <= total:
        r = call_json(endpoint, pagina=page, **params)
        if r.get("status") != "OK":
            print(f"  ! {endpoint} p{page}: {r.get('erros')}", file=sys.stderr)
            return
        total = int(r.get("numero_paginas", 1))
        print(f"  {endpoint} página {page}/{total}")
        for item in r.get(list_key, []):
            yield item[item_key]
        page += 1


def fetch_notas():
    notas = list(
        paginate("notas.fiscais.pesquisa.php", "notas_fiscais", "nota_fiscal")
    )
    (DATA / "notas.json").write_text(json.dumps(notas, ensure_ascii=False, indent=1))
    print(f"{len(notas)} notas fiscais")

    # O XML só existe para nota autorizada; pendente/cancelada não tem (ou não
    # interessa). `chave_acesso` presente é o sinal de que a SEFAZ autorizou.
    autorizadas = [n for n in notas if n.get("chave_acesso")]
    print(f"{len(autorizadas)} com chave de acesso → baixando XML")
    for i, n in enumerate(autorizadas, 1):
        dest = XMLS / f"{n['id']}.xml"
        if dest.exists():
            continue
        xml = call_xml_nota(n["id"])
        if not xml:
            print(f"  ! nota {n['id']}: sem XML após retries", file=sys.stderr)
            continue
        dest.write_text(xml, encoding="utf-8")
        if i % 25 == 0:
            print(f"  {i}/{len(autorizadas)} XMLs")
    return notas


def fetch_pedidos():
    pedidos = list(paginate("pedidos.pesquisa.php", "pedidos", "pedido"))
    print(f"{len(pedidos)} pedidos na listagem → obtendo detalhe (bloco ecommerce)")
    detalhes = []
    cache = DATA / "pedidos.json"
    if cache.exists():
        detalhes = json.loads(cache.read_text())
    visto = {d["id"] for d in detalhes}
    for i, p in enumerate(pedidos, 1):
        if p["id"] in visto:
            continue
        r = call_json("pedido.obter.php", id=p["id"])
        if r.get("status") == "OK":
            detalhes.append(r["pedido"])
        if i % 25 == 0:
            cache.write_text(json.dumps(detalhes, ensure_ascii=False, indent=1))
            print(f"  {i}/{len(pedidos)} pedidos")
    cache.write_text(json.dumps(detalhes, ensure_ascii=False, indent=1))
    return detalhes


def tabela(notas):
    """Tabela achatada de vendas — uma linha por nota."""
    cols = [
        "id", "tipo", "serie", "numero", "numero_ecommerce", "data_emissao",
        "situacao", "descricao_situacao", "chave_acesso", "nome",
        "cpf_cnpj", "uf", "cidade", "valor", "valor_produtos", "valor_frete",
    ]
    with (DATA / "notas.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for n in notas:
            cli = n.get("cliente", {})
            w.writerow({**n, "cpf_cnpj": cli.get("cpf_cnpj"),
                        "uf": cli.get("uf"), "cidade": cli.get("cidade")})
    print(f"→ {DATA / 'notas.csv'}")


if __name__ == "__main__":
    XMLS.mkdir(parents=True, exist_ok=True)
    only = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--only" else None

    notas = []
    if only in (None, "notas"):
        notas = fetch_notas()
        tabela(notas)
    if only in (None, "pedidos"):
        fetch_pedidos()
    print("pronto")
