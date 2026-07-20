from odoo import http
from odoo.http import request


class LiberSite(http.Controller):
    @http.route(["/liber", "/liber/"], type="http", auth="public")
    def liber(self, **kwargs):
        # O site é estático; o Odoo já serve /liber_site/static/* sozinho,
        # e os caminhos relativos (logo.png, img/...) resolvem sob esse prefixo.
        return request.redirect("/liber_site/static/index.html")
