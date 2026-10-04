# -*- coding: utf-8 -*-
{
    'name': 'Liber Training (o tile dos cursos)',
    'version': '19.0.1.0.0',
    'summary': 'A home tile that takes every internal user to the training courses',
    'description': """
Os cursos em vídeo do Liber moram no eLearning (website_slides), em /slides.
Na tela inicial, porém, o app eLearning só aparece para quem o edita (grupo
Officer): quem só assiste não tem porta.

Este módulo é a porta: um tile "Treinamento" na tela inicial dos aplicativos,
para todo usuário interno — menu raiz sem grupo, ação de URL para /slides na
mesma aba. Não cria curso, não muda o eLearning, não mexe em quem vê o quê.
""",
    'author': 'EdLab',
    'license': 'LGPL-3',
    'category': 'Website/eLearning',
    'depends': ['web', 'website_slides'],
    'data': [
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
