import os
import re

from odoo import http
from odoo.http import request

_STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
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


def _absolute(match):
    attr, url = match.group(1), match.group(2)
    caminho = _PREFIX + url
    arquivo = url.split("?", 1)[0].split("#", 1)[0]
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


class LiberSite(http.Controller):
    @http.route(["/liber", "/liber/"], type="http", auth="public")
    def liber(self, **kwargs):
        # Serve o HTML aqui em vez de redirecionar para /liber_site/static/:
        # assim o site também pode ser a home do domínio (website.homepage_url
        # = /liber faz o Odoo servir ESTE controller sem mudar a URL), e o
        # visitante fica em liber.edlab.press, não num caminho de asset.
        with open(os.path.join(_STATIC, "index.html"), encoding="utf-8") as fh:
            html = _RELATIVE_URL.sub(_absolute, fh.read())
        return request.make_response(
            html,
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-cache"),
            ],
        )
