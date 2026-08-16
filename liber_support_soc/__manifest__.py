# -*- coding: utf-8 -*-
{
    'name': 'Liber Support - Consignment Bridge',
    'version': '19.0.0.2.0',
    'summary': 'Links support tickets to the CO (consignment settlement) '
               'and answers with the consignment map',
    'description': """
A ponte entre o atendimento e a consignação.

O núcleo (``liber_support``) não sabe o que é consignação — de propósito.
Este módulo acrescenta ao chamado:

* o vínculo com a **CO** (``consignment.settlement``) e com o acordo
  (``consignment.agreement``);
* o botão **"Responder com o mapa"**: anexa o PDF do mapa de consignação
  do parceiro (o relatório do ``liber_soc_settlement``) a uma resposta.
  Com 99% do atendimento sendo consignação, essa macro é provavelmente
  metade do valor do módulo inteiro.

Se este módulo não estiver instalado, o chamado continua funcionando com
menos campos.
""",
    'author': 'EdLab Press',
    'category': 'Services/Support',
    'depends': ['liber_support', 'liber_soc_settlement'],
    'data': [
        'security/ir.model.access.csv',
        'views/support_ticket_views.xml',
        'wizard/co_from_conversation_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_support_soc/static/src/js/venda_wizard_tour.js',
            'liber_support_soc/static/src/js/ficha_vinculada_tour.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}
