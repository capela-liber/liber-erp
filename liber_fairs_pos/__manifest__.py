# -*- coding: utf-8 -*-
{
    'name': "Fairs — caixa do PDV na feira",
    'summary': "Um caixa de Ponto de Venda por feira, vendendo o estoque que está na mesa",
    'description': """
O caixa da feira.

Até aqui a feira sabia o que mandou, o que chegou e o que voltou; o que ela
NÃO sabia era o que vendeu, a não ser pela subtração do fechamento diário --
"tinha dez, contei seis, logo vendi quatro". É uma conta que fecha, mas não
sabe QUANDO, POR QUANTO nem PARA QUEM vendeu.

Esta ponte liga a feira ao Ponto de Venda do Odoo. Cada feira ganha o seu
caixa, e o caixa vende **o estoque que está na mesa**: a operação do PDV
nasce apontada para a localização daquela feira, e não para o armazém. Quem
está na praça vê a quantidade que tem ali, não a que existe a seiscentos
quilômetros.

O que isso muda no resto do módulo:

  - o movimento que o PDV gera nasce carimbado como VENDA DA FEIRA. Sem esse
    carimbo, a feira não veria a saída, o fechamento diário descontaria a
    mesma venda outra vez e a mesa terminaria negativa;
  - o fechamento diário deixa de ser a fonte da venda e passa a ser a
    CONFERÊNCIA dela: a diferença entre a contagem e o que o caixa registrou
    é exatamente o que se quer enxergar (venda não lançada, extravio);
  - a devolução no balcão devolve o exemplar para a mesa, e por isso conta
    com sinal negativo na venda.

O PDV funciona OFFLINE no navegador e sincroniza depois, o que numa feira com
wifi ruim não é detalhe.

O que este módulo NÃO faz, deliberadamente: cupom fiscal. A NFC-e depende de
CSC por empresa na Sefaz e será outra ponte. E a maquininha da InfinitePay
não tem driver de PDV no Odoo: ela entra como forma de pagamento digitada, e
a conciliação da taxa acontece depois, no financeiro.
""",
    'author': 'EdLab Press',
    'category': 'Inventory',
    'version': '19.0.8.0.0',
    'license': 'AGPL-3',
    # pos_discount: é ele que traz o desconto global com percentual
    # fixo, que é como a feira pratica desconto -- um número decidido no
    # cadastro do evento, e não um valor que cada um digita no balcão.
    'depends': ['liber_fairs', 'point_of_sale', 'pos_discount'],
    'data': [
        # A ficha da feira mostra os caixas dela e o que venderam. Sem estes
        # direitos de LEITURA, quem tem o papel de Feiras -- que é quem opera
        # a feira, e não o PDV da casa -- leva Access Error no primeiro
        # clique. Foi o tour de tela que pegou; o teste de ORM não vê.
        'security/fair_staff.xml',
        'security/ir.model.access.csv',
        'views/event_fair_views.xml',
        'views/event_fair_day_views.xml',
        'views/pos_config_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_fairs_pos/static/src/js/fair_pos_tour.js',
        ],
        'point_of_sale._assets_pos': [
            'liber_fairs_pos/static/src/js/fair_shelf.js',
            'liber_fairs_pos/static/src/js/product_card_fair_qty.js',
            'liber_fairs_pos/static/src/js/orderline_fair_price.js',
            'liber_fairs_pos/static/src/xml/product_card.xml',
            'liber_fairs_pos/static/src/xml/orderline.xml',
        ],
    },
    'installable': True,
    'auto_install': True,
    'application': False,
}
