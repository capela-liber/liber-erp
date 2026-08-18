#!/usr/bin/env python3
"""Compara, ANTES de escrever, o estoque do Olist com o do Odoo.

O push manda `tipo=B` — balanço absoluto: o número do Odoo **substitui** o do
Olist. Então a pergunta que decide se o push pode rodar não é "o código está
certo?", é: *o que exatamente muda em cada livro?* E uma classe de mudança é
perigosa de um jeito que as outras não são:

    livro com saldo no Olist e ZERO no Odoo → sai de circulação no marketplace

Isso acontece sem bug nenhum: basta o ISBN não casar, o exemplar estar em outra
empresa, ou a migração não ter trazido aquele saldo. Por isso a conferência é
read-only e roda antes: um relatório é barato, um catálogo zerado no meio da
semana não é.

Uso:
    python3 liber_olist/conferir_estoque.py [--snapshot ARQ] [--margem N]
                                            [--empresa 3] [--lot-stock 38]

Lê o Odoo de PRODUÇÃO por SSH (psql read-only, nenhum write).
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

DUMPS = Path.home() / "odoo_lab" / "dumps" / "olist"
SSH_ALVO = "macmini-liber@100.81.112.1"
PSQL = "/opt/homebrew/bin/psql -h localhost -U odoo_app -d prod -tAF'|'"


def ultimo_snapshot():
    fotos = sorted(DUMPS.glob("estoque-olist-*.json"))
    if not fotos:
        sys.exit(f"Nenhum snapshot em {DUMPS} — rode o snapshot_estoque.py antes.")
    return fotos[-1]


def estoque_odoo(lot_stock):
    """(barcode -> quantidade) na área de estoque do armazém, em produção.

    **LEFT JOIN, e a diferença decide o relatório.** Com `join` só voltam os
    códigos que têm saldo, e aí "não existe no Odoo" e "existe, zerado" caem no
    mesmo balde — sendo opostos: o que não existe nunca é tocado pelo push,
    e o que existe zerado É ZERADO no Olist. Todo produto com código de barras
    entra aqui, com 0 quando não há quant.

    `parent_path` em vez de recursão: é como o próprio Odoo resolve
    `child_of`, e traz as prateleiras endereçadas junto.
    """
    sql = f"""
with loc as (
  select id from stock_location
  where parent_path like (select parent_path from stock_location where id={lot_stock})||'%'
)
select p.barcode, coalesce(sum(q.quantity), 0)::numeric
from product_product p
left join stock_quant q
       on q.product_id = p.id and q.location_id in (select id from loc)
where p.barcode is not null
group by p.barcode;
"""
    saida = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=15", SSH_ALVO, f"{PSQL} <<'SQL'\n{sql}\nSQL"],
        capture_output=True, text=True, timeout=180)
    if saida.returncode != 0:
        sys.exit(f"psql falhou: {saida.stderr[:400]}")
    fora = {}
    for linha in saida.stdout.splitlines():
        if "|" not in linha:
            continue
        code, qtd = linha.rsplit("|", 1)
        try:
            fora[code.strip()] = float(qtd)
        except ValueError:
            continue
    return fora


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot")
    ap.add_argument("--margem", type=int, default=0)
    ap.add_argument("--lot-stock", type=int, default=38,
                    help="localização de estoque do armazém (EdLab = 38)")
    args = ap.parse_args()

    foto = Path(args.snapshot) if args.snapshot else ultimo_snapshot()
    dados = json.loads(foto.read_text(encoding="utf-8"))
    olist = {l["codigo"]: l for l in dados["linhas"] if l["codigo"]}
    odoo = estoque_odoo(args.lot_stock)

    print(f"snapshot : {foto.name} ({dados['gerado_em']})")
    print(f"Olist    : {len(olist)} produtos com código")
    print(f"Odoo     : {len(odoo)} códigos de barras (com ou sem saldo)\n")

    zerariam, subiriam, desceriam, iguais, sem_odoo = [], [], [], [], []
    for code, linha in olist.items():
        antes = float(linha["saldo"] or 0)
        bruto = odoo.get(code)
        if bruto is None:
            # Não existe produto com esse código de barras no Odoo. O espelho
            # do catálogo não vai mapear id nenhum, então o push NUNCA toca
            # nesses - ficam com o número que o Olist já tem. Sem risco, e
            # também sem sincronia: é dívida de dado, não de código.
            sem_odoo.append((code, antes, linha["nome"]))
            continue
        depois = max(0.0, bruto - args.margem)
        registro = (code, antes, depois, linha["nome"])
        if antes > 0 and depois == 0:
            zerariam.append(registro)
        elif depois > antes:
            subiriam.append(registro)
        elif depois < antes:
            desceriam.append(registro)
        else:
            iguais.append(registro)

    total_antes = sum(float(l["saldo"] or 0) for l in olist.values())
    tocados = len(iguais) + len(subiriam) + len(desceriam) + len(zerariam)
    print(f"margem aplicada: {args.margem}")
    print(f"\nO push TOCA {tocados} livros (têm produto no Odoo):")
    print(f"  iguais            : {len(iguais)}")
    print(f"  sobem             : {len(subiriam)}")
    print(f"  descem            : {len(desceriam)}")
    print(f"  ZERARIAM no Olist : {len(zerariam)}   <-- o grupo que decide")
    print(f"\nO push NÃO TOCA {len(sem_odoo)} (sem produto com esse código no Odoo),")
    print(f"  dos quais {sum(1 for _c, a, _n in sem_odoo if a > 0)} têm saldo no Olist hoje "
          f"({sum(a for _c, a, _n in sem_odoo):.0f} unidades que seguem à venda sem sincronia)")
    depois_total = (sum(d for _c, _a, d, _n in iguais + subiriam + desceriam + zerariam)
                    + sum(a for _c, a, _n in sem_odoo))
    print(f"\nunidades no Olist hoje : {total_antes:.0f}")
    print(f"unidades depois do push: {depois_total:.0f}")

    if zerariam:
        print("\nPrimeiros que zerariam (código, Olist hoje -> Odoo):")
        for code, antes, depois, nome in sorted(
                zerariam, key=lambda r: -r[1])[:15]:
            print(f"  {code}  {antes:6.0f} -> {depois:4.0f}  {nome[:48]}")

    destino = foto.with_name(foto.stem.replace("estoque-olist", "conferencia")
                             + ".csv")
    with destino.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["classe", "codigo", "olist_hoje", "odoo_enviaria", "nome"])
        for classe, grupo in (("zeraria", zerariam), ("desce", desceriam),
                              ("sobe", subiriam), ("igual", iguais)):
            for code, antes, depois, nome in grupo:
                w.writerow([classe, code, antes, depois, nome])
        for code, antes, nome in sem_odoo:
            w.writerow(["sem_saldo_no_odoo", code, antes, "", nome])
    print(f"\nCSV: {destino}")


if __name__ == "__main__":
    main()
