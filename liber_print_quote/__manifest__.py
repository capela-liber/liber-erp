# -*- coding: utf-8 -*-
{
    'name': 'Print Quote Specs',
    'version': '19.0.1.8.0',
    'summary': 'The book technical sheet travels on the RFQ the printer quotes',
    'description': """
A gráfica orça pelo que está no PDF. Sem formato, papel e acabamento, a cotação
volta como pergunta -- e cada volta é um dia. Este módulo põe a ficha técnica do
livro na linha do pedido de cotação e do pedido de compra.

Depende do liber_metabooks_integration porque é lá que a ficha mora: formato,
dimensões, número de páginas, encadernação e os acabamentos que a ONIX nomeia.
O que a norma NÃO nomeia -- laminação fosca contra brilho, reserva, verniz,
gramatura e tipo do papel do miolo -- entra aqui, em texto livre, porque a
Metabooks só aceita código de lista e não teria onde guardar.
""",
    'author': 'EdLab Press',
    'website': 'https://edlab.press',
    'license': 'AGPL-3',
    'category': 'Purchases',
    'depends': ['purchase', 'liber_metabooks_integration'],
    'data': [
        'views/product_template_views.xml',
        'report/purchase_templates.xml',
    ],
    'post_init_hook': 'traduzir_a_tela',
    'installable': True,
    'application': False,
}
