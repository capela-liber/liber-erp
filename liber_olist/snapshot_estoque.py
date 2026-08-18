#!/usr/bin/env python3
"""Fotografa (e devolve) o estoque de uma conta Olist/Tiny — API v2.

A rede de segurança do primeiro push de estoque para uma conta VIVA. Antes de
o Odoo virar o dono do saldo, guarda-se o saldo que o Olist tem hoje; se o push
sair errado, `--restore` reescreve exatamente o que estava lá.

Duas regras que fazem disso um backup de verdade, e não um arquivo bonito:

* **Ele volta.** Um snapshot sem caminho de volta é consolo, não seguro. O
  `--restore` manda os mesmos saldos de volta com `tipo=B` (balanço absoluto),
  produto a produto, e grava um log do que mandou.
* **Ele se recusa a mentir.** Produto com mais de um depósito não cabe num
  `tipo=B` sem depósito nomeado: o restore PARA em vez de achatar os depósitos
  num número só. Nesta conta há um depósito ("Geral"), mas isso é observação de
  hoje, não garantia.

Uso:
    python3 liber_olist/snapshot_estoque.py                 # fotografa
    python3 liber_olist/snapshot_estoque.py --restore ARQ   # ensaio (não escreve)
    python3 liber_olist/snapshot_estoque.py --restore ARQ --confirm   # escreve

Token: variável `TINY_TOKEN`; se ausente, lê a seção `# Olist` do CREDENCIAIS.md
do repositório (que é o que se tem à mão quando algo deu errado). Nunca é
impresso.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

API = "https://api.tiny.com.br/api2"

# A v2 limita por CONTA, e a conta é compartilhada com o próprio ERP e os
# marketplaces. 1,1 s (o que o módulo usa) NÃO bastou: a primeira tentativa
# morreu com "API Bloqueada - Excedido o número de acessos" no meio do
# catálogo. O teto da nossa conta não é determinável por documentação
# (NOTES.md §9.2 — as tabelas ainda usam nomes de plano legados), então o
# número aqui é empírico: 2,2 s cabe em 30 req/min, o piso da grade.
DELAY = 2.2

# "API Bloqueada" volta com HTTP 200 e status Erro — é throttle, não resposta.
# Recuar e insistir; nunca tratar como "não tem esse dado" (§6-bis, lição 2).
BLOQUEIO = "api bloqueada"
BACKOFF = 90

DEFAULT_OUT = Path.home() / "odoo_lab" / "dumps" / "olist"
REPO_CREDENTIALS = Path(__file__).resolve().parents[4] / "CREDENCIAIS.md"


def get_token():
    token = os.environ.get("TINY_TOKEN")
    if token:
        return token.strip()
    if REPO_CREDENTIALS.exists():
        text = REPO_CREDENTIALS.read_text(encoding="utf-8", errors="replace")
        if "# Olist" in text:
            section = text.split("# Olist", 1)[1].split("\n#", 1)[0]
            for line in section.splitlines():
                line = line.strip()
                if re.fullmatch(r"[A-Za-z0-9]{30,}", line):
                    return line
    sys.exit("Sem token: defina TINY_TOKEN ou destrave o CREDENCIAIS.md.")


def call(token, endpoint, **params):
    """POST na v2. Devolve o texto cru — nem todo endpoint responde JSON."""
    body = urllib.parse.urlencode(
        {"token": token, "formato": "json", **params}).encode()
    req = urllib.request.Request(
        f"{API}/{endpoint}", data=body, method="POST")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                out = resp.read().decode("utf-8", "replace")
            time.sleep(DELAY)
            return out
        except Exception as exc:
            wait = 5 * (attempt + 1)
            print(f"  ! {endpoint}: {exc} — retry em {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"{endpoint} falhou após 5 tentativas")


def call_json(token, endpoint, **params):
    """Como `call`, mas insistindo enquanto a resposta for estrangulamento.

    O erro de cota chega como HTTP 200 com `status: Erro` — se isso virasse
    exceção, uma foto de 600 produtos morreria na metade sempre que o ERP e os
    marketplaces estivessem ocupados. Erro de verdade (produto inexistente,
    token inválido) continua estourando na hora.
    """
    for attempt in range(8):
        raw = call(token, endpoint, **params)
        try:
            retorno = json.loads(raw).get("retorno", {})
        except ValueError:
            raise RuntimeError(f"{endpoint} não devolveu JSON: {raw[:200]}")
        if retorno.get("status") == "OK":
            return retorno
        detalhe = str(retorno.get("erros") or retorno.get("codigo_erro") or raw)
        if BLOQUEIO in detalhe.lower():
            espera = BACKOFF * (attempt + 1)
            print(f"  ~ cota estourada — pausa de {espera}s e continuo",
                  file=sys.stderr)
            time.sleep(espera)
            continue
        raise RuntimeError(f"{endpoint}: {detalhe}")
    raise RuntimeError(f"{endpoint}: bloqueado após 8 tentativas")


# ----------------------------------------------------------------------
# Fotografar
# ----------------------------------------------------------------------
def snapshot(token, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    # Retomável de propósito: ~600 chamadas a 2,2 s é meia hora de janela para
    # a cota estourar, a rede cair ou alguém fechar o terminal. Perder tudo e
    # recomeçar do zero é o que faz uma pessoa desistir do backup e empurrar
    # o estoque sem rede.
    parcial_path = out_dir / ".snapshot-parcial.json"
    feitos = {}
    if parcial_path.exists():
        feitos = json.loads(parcial_path.read_text(encoding="utf-8"))
        print(f"  retomando: {len(feitos)} produto(s) já lidos")

    produtos = []
    page, pages = 1, 1
    while page <= pages:
        ret = call_json(token, "produtos.pesquisa.php", pagina=page)
        pages = int(ret.get("numero_paginas") or 1)
        for item in ret.get("produtos", []):
            produtos.append(item["produto"])
        print(f"  catálogo: página {page}/{pages} ({len(produtos)} produtos)")
        page += 1

    for i, prod in enumerate(produtos, 1):
        pid = str(prod["id"])
        if pid in feitos:
            continue
        ret = call_json(token, "produto.obter.estoque.php", id=pid)
        est = ret.get("produto", {})
        feitos[pid] = {
            "id": pid,
            "codigo": (prod.get("codigo") or "").strip(),
            "nome": prod.get("nome") or "",
            "situacao": prod.get("situacao") or "",
            "unidade": est.get("unidade") or "",
            "saldo": est.get("saldo"),
            "saldo_reservado": est.get("saldoReservado"),
            "depositos": [d["deposito"] for d in (est.get("depositos") or [])],
        }
        if i % 25 == 0 or i == len(produtos):
            parcial_path.write_text(json.dumps(feitos, ensure_ascii=False),
                                    encoding="utf-8")
            print(f"  estoque: {i}/{len(produtos)}")

    linhas = [feitos[str(p["id"])] for p in produtos if str(p["id"]) in feitos]

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    base = out_dir / f"estoque-olist-{stamp}"
    payload = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "api": "tiny v2",
        "produtos": len(linhas),
        "total_unidades": sum(float(l["saldo"] or 0) for l in linhas),
        "linhas": linhas,
    }
    base.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    with base.with_suffix(".csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "codigo", "nome", "situacao", "unidade",
                         "saldo", "saldo_reservado", "depositos"])
        for l in linhas:
            writer.writerow([
                l["id"], l["codigo"], l["nome"], l["situacao"], l["unidade"],
                l["saldo"], l["saldo_reservado"],
                "; ".join("%s=%s" % (d.get("nome"), d.get("saldo"))
                          for d in l["depositos"]),
            ])

    multi = [l for l in linhas if len(l["depositos"]) > 1]
    print(f"\n{len(linhas)} produtos, {payload['total_unidades']:.0f} unidades.")
    print(f"JSON: {base.with_suffix('.json')}")
    print(f"CSV : {base.with_suffix('.csv')}")
    if multi:
        print(f"ATENÇÃO: {len(multi)} produto(s) com mais de um depósito — "
              f"o restore vai recusar esses (ver docstring).")
    # Só agora: enquanto a foto não está fechada em disco, o parcial é a única
    # cópia do que já custou meia hora de cota.
    parcial_path.unlink(missing_ok=True)
    return base.with_suffix(".json")


# ----------------------------------------------------------------------
# Devolver
# ----------------------------------------------------------------------
def restore(token, path, confirm, out_dir):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    linhas = payload["linhas"]
    multi = [l for l in linhas if len(l["depositos"]) > 1]
    if multi:
        sys.exit(
            f"{len(multi)} produto(s) têm mais de um depósito. Um balanço sem "
            f"depósito nomeado achataria o saldo deles — devolva esses à mão, "
            f"ou estenda o script para mandar o depósito. Primeiros: "
            + ", ".join(l["codigo"] for l in multi[:5]))

    total = sum(float(l["saldo"] or 0) for l in linhas)
    print(f"Snapshot de {payload['gerado_em']}: {len(linhas)} produtos, "
          f"{total:.0f} unidades.")
    if not confirm:
        print("ENSAIO — nada foi escrito. Repita com --confirm para devolver.")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    log_path = out_dir / f"restore-{stamp}.log"
    ok = erros = 0
    with log_path.open("w", encoding="utf-8") as log:
        for i, l in enumerate(linhas, 1):
            corpo = json.dumps({"estoque": {
                "idProduto": int(l["id"]),
                "tipo": "B",
                "quantidade": float(l["saldo"] or 0),
                "observacoes": "restore snapshot %s" % payload["gerado_em"][:10],
            }})
            raw = call(token, "produto.atualizar.estoque.php", estoque=corpo)
            try:
                status = json.loads(raw).get("retorno", {}).get("status")
            except ValueError:
                status = None
            if status == "OK":
                ok += 1
            else:
                erros += 1
            log.write(f"{l['id']}\t{l['codigo']}\t{l['saldo']}\t{status}\t"
                      f"{raw[:200]}\n")
            if i % 25 == 0 or i == len(linhas):
                print(f"  devolvido: {i}/{len(linhas)} ({erros} erro(s))")
    print(f"\n{ok} ok, {erros} com erro. Log: {log_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", metavar="ARQ",
                        help="devolve os saldos deste snapshot (JSON)")
    parser.add_argument("--confirm", action="store_true",
                        help="com --restore: escreve de verdade no Olist")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help=f"pasta de saída (padrão: {DEFAULT_OUT})")
    args = parser.parse_args()

    token = get_token()
    out_dir = Path(args.out).expanduser()
    if args.restore:
        restore(token, args.restore, args.confirm, out_dir)
    else:
        snapshot(token, out_dir)


if __name__ == "__main__":
    main()
