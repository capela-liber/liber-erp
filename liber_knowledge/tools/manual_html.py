"""Conversão dos manuais do Liber para HTML que sobrevive ao Odoo.

Os manuais moram em `liber_site/static/docs/*.html`, estilizados por
`docs.css`. Dentro do Odoo o CSS não chega: o `html_sanitize` remove a tag
`<style>`, e o editor de HTML do 19 reescreve o que não reconhece. Por isso
cada elemento sai com o estilo EMBUTIDO (`style="..."`), e o manual fica igual
ao do site onde quer que seja mostrado.

Dois consumidores, uma fonte só:

* `scripts/gen_module_descriptions.py` -- o `index.html` de Apps > Module Info;
* `liber_knowledge` -- as páginas do wiki (Conhecimento > Manuais do Liber).

Cada um decide para onde vão os links e as imagens sobrescrevendo `_href` e
`_src` do `Conversor`; o resto (paleta, mapa de estilos, callouts, capturas
que faltam) é o mesmo. Python puro: nada aqui importa o Odoo, e o gerador
roda fora dele.
"""

from __future__ import annotations

import html
import os
import re
from html.parser import HTMLParser


# Onde o manual completo continua morando, para o "ver no site" dos links
# cruzados. Caminho absoluto e com "static/" no meio: o Odoo não mexe nele.
URL_DOCS = "/liber_site/static/docs/"

# Paleta do docs.css. As variáveis CSS (var(--accent)) morreriam sem o :root,
# que vem no <style> que o sanitizador tira -- então aqui elas são literais.
PAPER = "#faf8fc"
PAPER2 = "#f1eaf6"
INK = "#251d2b"
INK_SOFT = "#5d5266"
ACCENT = "#6e2f91"
ACCENT_SOFT = "#8a4bad"
LOGO = "#c76ae1"
OK = "#2e6e4e"
LINE = "#e5dbee"

SANS = "Inter,'Segoe UI',system-ui,sans-serif"
TITULO = "'Space Grotesk','Segoe UI',system-ui,sans-serif"
MONO = "ui-monospace,Menlo,Consolas,monospace"

# tag -> style, aplicado a todo elemento daquele tipo.
ESTILOS_TAG = {
    "h1": f"font-family:{TITULO};font-size:32px;line-height:1.2;letter-spacing:-.015em;margin:0 0 10px;color:{INK};",
    "h2": f"font-family:{TITULO};font-size:24px;line-height:1.2;margin:40px 0 12px;padding-top:18px;border-top:1px solid {LINE};color:{INK};",
    "h3": f"font-family:{TITULO};font-size:19px;line-height:1.25;margin:28px 0 10px;color:{INK};",
    "h4": f"font-family:{TITULO};font-size:16px;line-height:1.3;margin:22px 0 8px;color:{INK};",
    "p": "margin:0 0 12px;",
    "ul": "margin:0 0 14px 22px;padding:0;",
    "ol": "margin:0 0 14px 22px;padding:0;",
    "li": "margin:0 0 7px;",
    "strong": f"color:{INK};",
    "a": f"color:{ACCENT};",
    "hr": f"border:0;border-top:1px solid {LINE};margin:32px 0;",
    "code": f"background:{PAPER2};border:1px solid {LINE};border-radius:5px;padding:1px 6px;font-size:13px;font-family:{MONO};",
    "pre": "background:#2b2233;color:#efe6f5;border-radius:12px;padding:16px 20px;overflow-x:auto;margin:0 0 16px;font-size:13px;line-height:1.6;",
    "table": "border-collapse:collapse;width:100%;margin:0 0 16px;font-size:14px;",
    "th": f"border:1px solid {LINE};padding:8px 12px;text-align:left;vertical-align:top;background:{PAPER2};font-family:{TITULO};font-size:13.5px;",
    "td": f"border:1px solid {LINE};padding:8px 12px;text-align:left;vertical-align:top;",
    "figure": "margin:20px 0 24px;",
    "figcaption": f"font-size:13px;color:{INK_SOFT};margin-top:10px;text-align:center;",
    "img": f"max-width:100%;display:block;margin:0 auto;border-radius:12px;border:1px solid {LINE};",
    "blockquote": f"margin:0 0 16px;padding-left:16px;border-left:3px solid {LINE};color:{INK_SOFT};",
}

# classe -> style, somado (e com prioridade) ao estilo da tag.
ESTILOS_CLASSE = {
    "lead": f"font-size:17.5px;color:{INK_SOFT};margin:0 0 26px;max-width:62ch;",
    "field": f"font-weight:600;color:{INK};",
    # A sigla explicada (<abbr class="sigla" title="...">). O sanitizador do
    # Odoo preserva <abbr> e o atributo title (conferido no html_sanitize do
    # 19), então o tooltip nativo continua; o "?" sobrescrito do site vem de
    # um ::after no docs.css, que não existe em CSS inline -- aqui fica só o
    # sublinhado pontilhado e o cursor de ajuda.
    "sigla": f"text-decoration:none;border-bottom:1px dotted {ACCENT_SOFT};cursor:help;",
    "menupath": f"display:inline-block;background:{PAPER2};border:1px solid {LINE};border-radius:6px;padding:1px 8px;font-size:13.5px;color:{INK};white-space:nowrap;",
    "tablewrap": "overflow-x:auto;margin:0 0 16px;",
    "seealso": f"border:1px solid {LINE};border-radius:12px;background:{PAPER2};padding:16px 20px;margin:32px 0 0;",
    "callout": f"border:1px solid {LINE};border-left:4px solid {ACCENT};border-radius:10px;background:{PAPER2};padding:14px 18px;margin:0 0 16px;",
    "tip": f"border-left-color:{OK};background:#eef5f0;border-color:#d8e7dd;",
    "warn": "border-left-color:#b3831a;background:#faf3e3;border-color:#eddfba;",
    "example": f"border-left-color:{LOGO};",
    "steps": "margin:0 0 16px 22px;padding:0;",
}

# A cor do rótulo ("NOTA", "DICA"...) depende da variante do callout em volta,
# que o CSS resolvia com seletor descendente. Aqui é um empilhamento manual.
COR_TITULO = {
    "note": ACCENT,
    "tip": OK,
    "warn": "#7a5a12",
    "example": ACCENT_SOFT,
    "seealso": INK_SOFT,
}

# Só faz sentido no site: navegação, migalha de pão e o script da sidebar.
DESCARTAR = (
    ("div", "breadcrumb"),
    ("nav", "pager"),
    ("aside", "sidebar"),
    ("header", "top"),
)

VAZIAS = {"img", "br", "hr", "input", "meta", "link", "source"}

RE_ARTIGO = re.compile(
    r'<article class="doc">(.*?)</article>', re.DOTALL | re.IGNORECASE
)
RE_TITULO_PAGINA = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.IGNORECASE)


def _classes(attrs: dict) -> list[str]:
    return (attrs.get("class") or "").split()


def _escapar(valor: str) -> str:
    """Escapa o mínimo para caber num atributo entre aspas duplas.

    `html.escape(quote=True)` também troca a aspa simples por `&#x27;`, e os
    estilos aqui são cheios de `font-family:'Space Grotesk'` -- viraria uma
    sopa ilegível no arquivo gerado, sem ganho nenhum de segurança.
    """
    return valor.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _juntar_estilo(partes: list[str]) -> str:
    """Junta declarações CSS deixando só a última de cada propriedade.

    A classe vem depois da tag, então `p.lead` sobrescreve a margem de `p` --
    a mesma ordem de precedência que o docs.css tinha.
    """
    props: dict[str, str] = {}
    for parte in partes:
        for decl in parte.split(";"):
            decl = decl.strip()
            if not decl or ":" not in decl:
                continue
            nome, _, valor = decl.partition(":")
            nome = nome.strip()
            props.pop(nome, None)          # reposiciona no fim
            props[nome] = valor.strip()
    return "".join(f"{k}:{v};" for k, v in props.items())


class Conversor(HTMLParser):
    """Reescreve o corpo do manual com o CSS embutido em cada elemento."""

    def __init__(self, modulo: str, base: str):
        super().__init__(convert_charrefs=False)
        self.modulo = modulo
        # Pasta onde os caminhos relativos do manual (img/...) resolvem: o
        # site, ou a pasta doc/ do próprio módulo quando ele não é publicado.
        self.base = base
        self.saida: list[str] = []
        self.imagens: set[str] = set()
        self.faltando: list[tuple[str, str]] = []
        self._pular = 0          # profundidade dentro de um bloco descartado
        self._pilha: list[str] = []   # nomes das tags abertas
        self._callout: list[str] = []  # variante do callout/seealso corrente
        self._em_pre = 0

    # -- helpers ---------------------------------------------------------
    def _estilo(self, tag: str, attrs: dict) -> str:
        classes = _classes(attrs)
        partes = []
        base = ESTILOS_TAG.get(tag)
        if base:
            partes.append(base)
        # <code> dentro de <pre> não leva a caixinha clara do código inline.
        if tag == "code" and self._em_pre:
            partes = ["background:none;border:0;padding:0;color:inherit;font-size:inherit;"]
        # A moldura da captura é do <figure class="shot">; imagem solta no meio
        # do texto (um ícone, por exemplo) não leva borda nem centralização.
        if tag == "img" and (not self._pilha or self._pilha[-1] != "figure"):
            partes.append("border:0;margin:0;display:inline;")
        for c in classes:
            extra = ESTILOS_CLASSE.get(c)
            if extra:
                partes.append(extra)
        # o <i> separador do caminho de menu
        if tag == "i" and self._pilha and self._pilha[-1] == "span":
            partes.append(f"font-style:normal;color:{ACCENT};margin:0 4px;font-weight:700;")
        # rótulo do callout / do "ver também"
        if "title" in classes:
            cor = COR_TITULO.get(self._callout[-1] if self._callout else "note", ACCENT)
            partes.append(
                "font-weight:700;font-size:12px;letter-spacing:.08em;"
                f"text-transform:uppercase;display:block;margin:0 0 4px;color:{cor};"
            )
        if tag == "strong" and self._pilha and self._pilha[-1] == "div" and self._callout and self._callout[-1] == "seealso":
            partes.append(
                "font-weight:700;font-size:12px;letter-spacing:.08em;"
                f"text-transform:uppercase;display:block;margin:0 0 8px;color:{INK_SOFT};"
            )
        antigo = attrs.get("style")
        if antigo:
            partes.append(antigo.rstrip(";") + ";")
        return _juntar_estilo(partes)

    def _href(self, url: str) -> str:
        """Link entre manuais aponta para o manual publicado; âncora fica."""
        if url.startswith(("#", "http://", "https://", "mailto:", "tel:", "/")):
            return url
        if url.startswith("../"):
            return "/liber_site/static/" + url[3:]
        return URL_DOCS + url

    def _src(self, url: str) -> str | None:
        """Copia a captura para dentro do módulo e devolve o caminho local.

        Devolve None quando o arquivo não existe (captura ainda não feita):
        o chamador põe um espaço reservado no lugar, como o docs.js faz no
        site -- aqui não há JavaScript para consertar depois.
        """
        arquivo = url.split("?", 1)[0].split("#", 1)[0]
        origem = os.path.normpath(os.path.join(self.base, arquivo))
        if not origem.startswith(self.base + os.sep) or not os.path.isfile(origem):
            return None
        self.imagens.add(arquivo)
        return arquivo

    def _emitir(self, texto: str) -> None:
        if not self._pular:
            self.saida.append(texto)

    # -- HTMLParser ------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        d = {k: (v or "") for k, v in attrs}
        if self._pular:
            if tag not in VAZIAS:
                self._pular += 1
            return
        for alvo, classe in DESCARTAR:
            if tag == alvo and classe in _classes(d):
                self._pular = 1 if tag not in VAZIAS else 0
                return
        if tag == "script":
            self._pular = 1
            return

        if tag == "pre":
            self._em_pre += 1
        classes = _classes(d)
        if "callout" in classes:
            variante = next((c for c in classes if c in COR_TITULO), "note")
            self._callout.append(variante)
        elif "seealso" in classes:
            self._callout.append("seealso")

        if tag == "img":
            local = self._src(d.get("src", ""))
            if local is None:
                self.faltando.append((d.get("src", ""), d.get("alt", "")))
                self._emitir(self._placeholder(d))
                return
            d["src"] = local
        elif tag == "a" and "href" in d:
            destino = self._href(d["href"])
            d["href"] = destino
            if not destino.startswith("#"):
                d["target"] = "_blank"
                d["rel"] = "noopener"

        estilo = self._estilo(tag, d)
        if estilo:
            d["style"] = estilo
        pedacos = "".join(f' {k}="{_escapar(v)}"' for k, v in d.items() if v)
        self._emitir(f"<{tag}{pedacos}>")
        if tag not in VAZIAS:
            self._pilha.append(tag)

    def _placeholder(self, d: dict) -> str:
        alt = html.escape(d.get("alt", ""))
        arquivo = html.escape(d.get("src", ""))
        return (
            f'<div style="border:2px dashed {LINE};border-radius:12px;background:{PAPER};'
            f'color:{INK_SOFT};font-size:13px;text-align:center;padding:28px 20px;">'
            f'<div style="font-size:24px;margin-bottom:6px;">📷</div>'
            f"<div>Tela a inserir: <code style=\"background:{PAPER2};border:1px solid {LINE};"
            f'border-radius:5px;padding:1px 6px;font-family:{MONO};">{arquivo}</code></div>'
            f'<div style="margin-top:6px;">{alt}</div></div>'
        )

    def handle_endtag(self, tag):
        if self._pular:
            self._pular -= 1
            return
        if tag == "pre" and self._em_pre:
            self._em_pre -= 1
        if self._pilha and self._pilha[-1] == tag:
            self._pilha.pop()
        elif tag in self._pilha:
            while self._pilha and self._pilha.pop() != tag:
                pass
        if tag in ("div", "aside") and self._callout:
            self._callout.pop()
        if tag not in VAZIAS:
            self._emitir(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        self._emitir(data)

    def handle_entityref(self, name):
        self._emitir(f"&{name};")

    def handle_charref(self, name):
        self._emitir(f"&#{name};")

    def handle_comment(self, data):
        pass
