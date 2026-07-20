from . import controllers


def post_init_hook(env):
    """Aponta a home do site para /liber, se o módulo `website` estiver por perto.

    Sem isso, a raiz do domínio cai na home do website builder ("My Website")
    e o site do Liber fica escondido em /liber. Com homepage_url definido, o
    Odoo serve ESTE controller sem trocar a URL (website/controllers/main.py,
    Website.index -> request.reroute).

    Só preenche quando está vazio: se alguém escolheu outra home de propósito,
    a escolha fica de pé.
    """
    websites = env["ir.model"].sudo().search([("model", "=", "website")])
    if not websites:
        return  # `website` não instalado; o site segue em /liber e pronto
    for website in env["website"].sudo().search([("homepage_url", "in", [False, ""])]):
        website.homepage_url = "/liber"
