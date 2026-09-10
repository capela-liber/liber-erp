# -*- coding: utf-8 -*-
{
    'name': "Fairs — filtros da Metabooks",
    'summary': "Monta a grade da feira pelos campos do catálogo: assunto Thema e data de publicação",
    'description': """
A ponte entre as feiras e o catálogo da Metabooks.

O módulo de feiras não exige a Metabooks para existir: uma feira é uma
remessa temporária, e isso vale para quem vende livro catalogado e para quem
não vende. Mas quem TEM o catálogo monta a grade muito melhor, porque pode
pedir por assunto e por época em vez de por nome.

O que esta ponte acrescenta ao assistente "Somar títulos":

  - **assunto Thema**, com o galho inteiro: escolher o Y traz todo o
    infantojuvenil, e não só o código exato;
  - **faixa de data de publicação**, que é o que separa lançamento de fundo
    de catálogo;
  - a ordem **mais novos primeiro**, que só faz sentido onde existe data de
    publicação.

Nada disso é campo novo: tudo já está no produto, posto lá pela importação
da Metabooks. O que faltava era poder perguntar por eles na hora de escolher
o que vai para a mesa.
""",
    'author': 'EdLab Press',
    'category': 'Inventory',
    'version': '19.0.1.0.0',
    'license': 'AGPL-3',
    'depends': ['liber_fairs', 'liber_metabooks_integration'],
    'data': [
        'views/event_fair_add_products_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'application': False,
}
