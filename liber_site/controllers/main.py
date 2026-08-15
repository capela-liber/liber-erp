import os
import re

from odoo import http
from odoo.http import request

_STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
_DOCS = os.path.join(_STATIC, "docs")
_PREFIX = "/liber_site/static/"

# Caminhos relativos do HTML (logo.png, img/..., docs/index.html) viram
# absolutos sob o prefixo do módulo. Ficam de fora âncoras, caminhos já
# absolutos e URLs externas.
#
# Um <base href> faria o mesmo com uma linha, mas quebraria as âncoras da
# navegação (#consignacao, #direitos, ...): com <base>, "#secao" resolve
# contra a URL base e tira o visitante da raiz.
_RELATIVE_URL = re.compile(r'\b(src|href)="(?!/|#|https?:|mailto:|tel:|data:)([^"]+)"')

# O Odoo serve /<módulo>/static/* com Cache-Control: max-age=604800. Atrás da
# Cloudflare isso vira uma semana de imagem velha no ar depois de cada troca.
# Assets ganham ?v=<mtime>, então trocar o arquivo troca a URL e o cache antigo
# simplesmente deixa de ser consultado. Links de página ficam de fora: ninguém
# quer clicar em "Manuais" e ver ?v=... na barra de endereço.
_ASSET_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".ico")


def _absolute(match, pasta=""):
    """`pasta` é onde o documento vive dentro de static/ (vazio na raiz,
    "docs/" nos manuais): um href="docs.css" escrito num manual precisa virar
    /liber_site/static/docs/docs.css, não /liber_site/static/docs.css."""
    attr, url = match.group(1), match.group(2)
    url = pasta + url
    caminho = _PREFIX + url
    arquivo = url.split("?", 1)[0].split("#", 1)[0]

    # Páginas (a landing e os manuais) vão pelas rotas /liber e /liber/docs,
    # que respondem sem cache. Só os assets seguem por /liber_site/static,
    # onde uma semana de cache é o que se quer -- eles têm ?v= para trocar.
    limpo = os.path.normpath(arquivo).replace(os.sep, "/") if arquivo else ""
    if limpo.lower().endswith(".html") and not limpo.startswith(".."):
        resto = url[len(arquivo):]
        if limpo == "index.html":
            return f'{attr}="/liber{resto}"'
        if limpo.startswith("docs/"):
            return f'{attr}="/liber/{limpo}{resto}"'
    if arquivo.lower().endswith(_ASSET_EXT):
        alvo = os.path.normpath(os.path.join(_STATIC, arquivo))
        # normpath resolve ".."; sem esta checagem um caminho no HTML poderia
        # apontar para fora de static/.
        if alvo.startswith(_STATIC + os.sep):
            try:
                caminho += ("&" if "?" in caminho else "?") + f"v={int(os.stat(alvo).st_mtime):x}"
            except OSError:
                pass  # arquivo ainda não existe; serve sem versão e 404 como antes
    return f'{attr}="{caminho}"'


def _pagina(caminho, pasta=""):
    """Lê o HTML do disco e devolve a resposta já reescrita e sem cache.

    O `no-cache` é o ponto: o Odoo serve /<módulo>/static/* com
    max-age=604800, e atrás da Cloudflare isso significa que uma correção de
    texto pode levar uma semana para chegar ao leitor. Servir a página por
    aqui tira o HTML dessa regra; os assets continuam com cache longo, mas
    ganham ?v=<mtime> e trocam de URL quando mudam."""
    with open(caminho, encoding="utf-8") as fh:
        html = _RELATIVE_URL.sub(lambda m: _absolute(m, pasta), fh.read())
    return request.make_response(
        html,
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Cache-Control", "no-cache"),
        ],
    )


class LiberSite(http.Controller):
    @http.route(["/liber", "/liber/"], type="http", auth="public")
    def liber(self, **kwargs):
        # Serve o HTML aqui em vez de redirecionar para /liber_site/static/:
        # assim o site também pode ser a home do domínio (website.homepage_url
        # = /liber faz o Odoo servir ESTE controller sem mudar a URL), e o
        # visitante fica em liber.edlab.press, não num caminho de asset.
        return _pagina(os.path.join(_STATIC, "index.html"))

    @http.route("/liber/docs", type="http", auth="public")
    def liber_docs_raiz(self, **kwargs):
        """Sem a barra final, o navegador resolve os links que o docs.js
        escreve no cliente (liber_budget.html) contra /liber/, não contra
        /liber/docs/ — e todo manual da lista dá 404. A barra não é enfeite."""
        return request.redirect("/liber/docs/", code=301)

    @http.route(
        ["/liber/docs/", "/liber/docs/<string:pagina>"],
        type="http", auth="public",
    )
    def liber_docs(self, pagina="index.html", **kwargs):
        """Os manuais pela mesma porta da landing.

        Antes só existia /liber_site/static/docs/..., e o README anunciava
        /liber/docs, que devolvia 404. Pior que o 404: servido como asset, o
        índice vinha com uma semana de cache e um docs.js sem versão — quem
        tinha aberto a página antes continuava vendo a lista velha, sem os
        manuais novos, e concluía que o manual não tinha subido."""
        if not pagina.endswith(".html"):
            pagina += ".html"
        alvo = os.path.normpath(os.path.join(_DOCS, pagina))
        # normpath resolve "..": sem esta checagem, /liber/docs/..%2findex.html
        # leria arquivo de fora da pasta dos manuais.
        if not alvo.startswith(_DOCS + os.sep) or not os.path.isfile(alvo):
            return request.not_found()
        return _pagina(alvo, "docs/")
