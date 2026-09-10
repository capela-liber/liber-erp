# -*- coding: utf-8 -*-
{
    'name': "Events — feiras, bienais e lançamentos",
    'summary': "A feira é remessa temporária, não venda: sai, vende em parte na praça, e volta incompleta",
    'description': """
Feira não é venda.

É uma remessa temporária: o estoque sai da editora, fica dias sob a guarda de
outra pessoa, vende em parte num PDV que não é o ERP, e volta incompleto — com
sobra, perda, avaria e dinheiro a conciliar. Passar isso pelo fluxo de venda
comum produz três distorções: baixa estoque no envio, quando ainda é da
editora; reconhece receita antes de existir venda; e não deixa rastro nenhum
entre o que foi, o que vendeu e o que voltou.

Este módulo isola o ciclo num objeto próprio. O que está aqui hoje são as duas
primeiras fases de _mds/modulo-eventos-feiras.md.

O EVENTO (fase 1)
  - `event.fair`, com número próprio E00001 em série separada da venda — o que
    torna trivial filtrar feira em qualquer relatório e impede que evento
    contamine numeração, comissão e meta de venda;
  - calendário, lista e busca por selo, praça, canal, responsável e estado;
  - a grade título a título, com o planejado digitado e o resto deduzido dos
    movimentos.

O ESTOQUE (fase 2)
  - cada feira ganha sua localização sob a raiz FEIRAS, que fica FORA da
    árvore do armazém: o que está na praça continua sendo nosso e mantém valor
    no balanço, mas não infla o "Em mãos" com exemplar que ninguém pode vender
    pelo site nem despachar para livraria;
  - tipos de operação próprios, separados da entrega de venda e da
    consignação: FEIRA/OUT (remessa), FEIRA/IN (retorno), FEIRA/VND (venda na
    praça) e FEIRA/PRD (perda);
  - todo movimento passa por stock.picking / stock.move, nunca por escrita
    direta em stock.quant — é o que dá o rastro;
  - o saldo da localização responde, a qualquer momento, o que está
    fisicamente naquela mesa.

REPOSIÇÃO E FECHAMENTO DIÁRIO
  - evento de vários dias pede reposição no meio: aumenta-se a quantidade
    planejada da linha e despacha-se de novo. Sai um segundo movimento contra
    a MESMA localização. Uma feira, N remessas, um saldo só;
  - e não se apura só no fim. Todo dia, quando a praça fecha, conta-se o que
    sobrou na mesa. O sistema não pergunta o que vendeu: ele deduz, porque
    sabe o que estava lá na abertura e o que entrou de reposição no meio —
    vendido no dia = saldo na abertura + reposição − contagem do fim. Fechar o
    dia gera o movimento de venda, e por isso o saldo volta a bater com a mesa
    física todo fim de dia, em vez de só bater no acerto final, semanas
    depois.

O QUE AINDA NÃO ESTÁ AQUI
  A nota de simples remessa e os CFOPs (§3.4), o template de curadoria da
  grade (§3.5), a importação do CSV do PDV (§3.6), o faturamento após o
  retorno (§3.7), a classificação de avaria e extravio (§3.8) e o painel de
  retorno do canal (§3.9). O dinheiro ainda não passa por este módulo: o
  fechamento diário move estoque e nada mais. Quando o CSV do PDV chegar, é
  contra o número diário daqui que o extrato da maquininha vai ser conferido,
  e a divergência aparece no dia em que nasceu, em vez de somada e
  indecifrável no fim.
""",
    'author': 'EdLab Press',
    'category': 'Inventory',
    'version': '19.0.6.0.0',
    'license': 'AGPL-3',
    'depends': ['stock', 'mail', 'sales_team'],
    'data': [
        'security/liber_fairs_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/event_fair_template_views.xml',
        'views/event_fair_loss_views.xml',
        'views/fair_receipt_views.xml',
        'views/event_fair_views.xml',
        'views/event_fair_day_views.xml',
        'views/stock_picking_views.xml',
        'views/res_config_settings_views.xml',
        'views/liber_fairs_menus.xml',
        'data/liber_roles_bridge.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_fairs/static/src/css/fair_day.css',
            'liber_fairs/static/src/js/fair_template_tour.js',
            'liber_fairs/static/src/js/fair_full_tour.js',
            'liber_fairs/static/src/js/fair_losses_tour.js',
        ],
    },
    'installable': True,
    'application': True,
}
