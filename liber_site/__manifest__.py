{
    "name": "Liber Site",
    "summary": "Site de apresentação do Liber, servido em /liber",
    "description": """
Serve o site estático de apresentação do Liber (pasta static/) na rota /liber.
A fonte do site é a pasta _web/ na raiz do repositório; após editar lá,
sincronize com: cp -r _web/index.html _web/logo.png _web/img liber_site/static/
""",
    "version": "19.0.1.0.0",
    "author": "Edlab",
    "category": "Website",
    "license": "LGPL-3",
    "depends": ["web"],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
