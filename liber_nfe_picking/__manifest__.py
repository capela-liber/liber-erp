# -*- coding: utf-8 -*-
{
    'name': "NFe — DANFE na transferência",
    'summary': "A logística vê a DANFE no próprio movimento, sem abrir o Faturamento",
    'description': """
A DANFE onde a logística trabalha.

Quem embala e despacha vive na transferência (stock.picking), não na fatura —
e não deve precisar do app Faturamento para pegar o documento que viaja com a
caixa. Este módulo leva a DANFE até lá:

  - quando a SEFAZ autoriza a NFe (via ``liber_nfe_focus``), o PDF da DANFE é
    postado no chatter de cada transferência do pedido por trás da nota, e a
    transferência ganha o vínculo com a nota (número e situação na ficha);
  - se a nota for cancelada depois, o chatter avisa — o PDF anexado não pode
    ficar mentindo sozinho no registro;
  - a lista de transferências ganha os filtros "Com nota fiscal" e "Sem nota
    fiscal", para separar o que já pode viajar do que ainda espera emissão;
  - o menu Imprimir da lista ganha "Notas fiscais": seleciona os movs e as
    DANFEs saem num PDF só, prontas para a bancada de expedição. Seleção com
    mov sem nota não imprime pela metade — avisa qual falta.

O caminho da nota até a transferência tem duas pernas, e cobre os três casos
que têm movimento físico:

  venda (S000)        linhas da fatura -> linhas do pedido -> transferências
  consignação (C000)  a nota REM/ nasce sem linha ligada ao pedido; o elo é o
  e remessa (REM)     ``invoice_origin``, que o gerador carimba com o nome do SO

O acerto (CO) fatura sem transferência — os livros já estão na prateleira do
cliente — e por isso não passa por aqui: nenhuma perna o alcança, de propósito.

Pela mesma ponte viajam VOLUMES E PESO. A nota fiscal precisa declarar
quantas caixas vão e quanto pesam: a caixa quem conta é quem embala, na
transferência; o peso o Odoo soma dos produtos, e quem fatura corrige
quando o cadastro não tem. Nota com movimentação não é emitida sem os dois
— e o acerto, que não move caixa nenhuma, passa direto.

Falha na propagação nunca derruba a emissão: a nota já está autorizada na
SEFAZ, e o aviso à logística se refaz na próxima consulta do cron.
""",
    'author': 'EdLab Press',
    'category': 'Inventory',
    'version': '19.0.2.6.0',
    'license': 'AGPL-3',
    # liber_transport traz a contagem de caixas na transferência (box_count),
    # que é o que a nota declara e a transportadora confere na coleta.
    'depends': ['liber_nfe_focus', 'liber_transport', 'sale_stock'],
    'data': [
        'views/stock_picking_views.xml',
        'views/account_move_views.xml',
        'views/sale_order_views.xml',
        'report/stock_picking_report.xml',
    ],
    'installable': True,
}
