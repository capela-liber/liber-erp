"""Os manuais do site, prontos para virar páginas do wiki.

Duas peças, ambas Python puro (o teste roda sem banco):

* `ler_catalogo` lê o `DOCS` do `docs.js` -- a mesma lista de áreas e
  manuais que monta a barra lateral do site. É ela que dá a árvore do wiki:
  área vira categoria, manual vira página, na ordem em que o site mostra.
* `converter_manual` passa o `<article class="doc">` pelo `Conversor` do
  Module Info, trocando só o destino de links e capturas: link para outro
  manual aponta para a página do wiki; captura aponta para o arquivo que o
  `liber_site` já publica em `/liber_site/static/docs/img/`.
"""

from __future__ import annotations

import hashlib
import os
import re

try:  # dentro do Odoo, como pacote do módulo
    from . import manual_html
except ImportError:  # fora dele (scripts, testes soltos)
    import manual_html  # type: ignore[no-redef]

URL_DOCS = manual_html.URL_DOCS

RE_DOCS = re.compile(r"var\s+DOCS\s*=\s*\[(.*?)\n\];", re.DOTALL)
RE_AREA = re.compile(
    r'\{\s*area:\s*"((?:[^"\\]|\\.)*)",\s*desc:\s*"((?:[^"\\]|\\.)*)",\s*items:\s*\[(.*?)\]\s*\}',
    re.DOTALL,
)
RE_ITEM = re.compile(
    r'\{\s*slug:\s*"([^"]+)",\s*title:\s*"((?:[^"\\]|\\.)*)",\s*desc:\s*"((?:[^"\\]|\\.)*)"',
    re.DOTALL,
)


RE_H1 = re.compile(r"<h1\b[^>]*>.*?</h1>", re.DOTALL | re.IGNORECASE)


def _js(texto: str) -> str:
    """Desfaz o escape de string JS que o catálogo usa (só aspas e barra)."""
    return texto.replace('\\"', '"').replace("\\\\", "\\")


def ler_catalogo(texto_js: str) -> list[dict]:
    """[{area, desc, items: [{slug, title, desc}]}], na ordem do site.

    Levanta ValueError se não achar o `var DOCS = [...]` ou se ele vier vazio:
    um catálogo que não se lê não pode virar um wiki vazio calado.
    """
    bloco = RE_DOCS.search(texto_js)
    if not bloco:
        raise ValueError("docs.js sem o catálogo 'var DOCS = [...]'")
    areas = []
    for area, desc, itens in RE_AREA.findall(bloco.group(1)):
        areas.append({
            "area": _js(area),
            "desc": _js(desc),
            "items": [
                {"slug": s, "title": _js(t), "desc": _js(d)}
                for s, t, d in RE_ITEM.findall(itens)
            ],
        })
    if not any(a["items"] for a in areas):
        raise ValueError("o catálogo do docs.js não tem nenhum manual")
    return areas


def assinatura(conteudo: str) -> str:
    return hashlib.sha1((conteudo or "").encode("utf-8")).hexdigest()


class ConversorWiki(manual_html.Conversor):
    """O conversor do Module Info, com links e capturas apontando para o Odoo.

    `links` mapeia o slug de cada manual para a URL da página no wiki. Um
    link para manual que não está no mapa continua indo para o site.
    """

    def __init__(self, modulo: str, base: str, links: dict[str, str]):
        super().__init__(modulo, base)
        self.links = links

    def _href(self, url: str) -> str:
        if not url.startswith(("#", "http://", "https://", "mailto:", "tel:", "/", "../")):
            arquivo, _, ancora = url.partition("#")
            slug = arquivo[:-5] if arquivo.endswith(".html") else arquivo
            if slug in self.links:
                return self.links[slug] + (f"#{ancora}" if ancora else "")
        return super()._href(url)

    def _src(self, url: str) -> str | None:
        arquivo = url.split("?", 1)[0].split("#", 1)[0]
        origem = os.path.normpath(os.path.join(self.base, arquivo))
        if not origem.startswith(self.base + os.sep) or not os.path.isfile(origem):
            return None
        self.imagens.add(arquivo)
        return URL_DOCS + os.path.relpath(origem, self.base).replace(os.sep, "/")


def converter_manual(caminho: str, slug: str, links: dict[str, str]) -> str:
    """O corpo do manual em HTML com estilo embutido, pronto para a página."""
    with open(caminho, encoding="utf-8") as fh:
        fonte = fh.read()
    m = manual_html.RE_ARTIGO.search(fonte)
    if not m:
        raise ValueError(f'{slug}: sem <article class="doc"> em {caminho}')
    conv = ConversorWiki(slug, os.path.dirname(caminho), links)
    conv.feed(m.group(1))
    conv.close()
    corpo = "".join(conv.saida).strip()
    # O título da página do wiki já é o nome do manual; o <h1> repetiria.
    corpo = RE_H1.sub("", corpo, count=1).lstrip()
    abre = (
        '<div class="liber_manual" style="max-width:900px;padding:8px 4px 24px;'
        f'color:{manual_html.INK};font:15px/1.7 {manual_html.SANS};">'
    )
    return abre + corpo + "</div>"
