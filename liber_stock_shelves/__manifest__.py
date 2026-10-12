# -*- coding: utf-8 -*-
{
    'name': "Prateleiras — locais de armazenamento e transferências internas",
    'summary': "A prateleira volta a aparecer na tela, e o livro passa a poder "
               "mudar de prateleira",
    'description': """
O armazém da casa é endereçado: cada livro tem a sua prateleira
(``EL-VG/Stock/EL-000137``), e a migração de 28/07/2026 trouxe as prateleiras
e o que há em cada uma. O que a migração NÃO trouxe foi o interruptor do Odoo
que as mostra -- "Locais de armazenamento", em Inventário > Configuração >
Definições. Com ele desligado:

  - a transferência esconde os campos De/Para, a ficha do livro esconde a
    coluna Localização e o relatório de estoque mostra tudo como um local só;
  - o Odoo arquiva o tipo de operação "Transferência interna" (INT) de cada
    armazém, e some o único caminho de tela para mover um livro de uma
    prateleira para outra.

No Odoo 15 o interruptor estava ligado para todos os 45 usuários, e havia
18.283 transferências internas validadas. No 19, zero usuários -- o gerente
comercial foi o primeiro a sentir falta, mas ninguém via.

Este módulo faz do interruptor uma decisão de código, para que ela suba com
o deploy e não morra na próxima renovação do dev a partir do prod:

  - ``data/res_groups.xml`` faz o grupo "Usuário interno" implicar o grupo de
    locais de armazenamento, que é exatamente o que a caixinha das Definições
    faz. Quem desmarcar a caixinha vê o módulo marcá-la de novo no próximo
    ``-u``: a decisão mora aqui, não na tela;
  - o gancho de instalação reativa a Transferência interna de cada armazém
    (o core só faz isso quando a caixinha é clicada por um administrador do
    Inventário) e apaga as duas views que tiravam o botão Criar da lista de
    locais, como o core faria.

A ARMADILHA DA RAIZ (08/10/2026). A transferência interna nasce com a raiz
do armazém nos dois campos; deixada na origem, a reserva desce a árvore e
separa da prateleira que recebeu primeiro -- muitas vezes a de destino -- e
a linha fica dela para ela mesma: valida e nada se move (picking 9204 do
dev). O módulo recusa validar linha interna com origem igual ao destino,
nomeando a prateleira, e mostra a coluna "Separar de" na linha da
transferência interna para o engano aparecer antes do clique.

O que NÃO muda: os tipos COM/MOV da consignação continuam arquivados (são
outro tipo, não o INT do armazém), e nenhum grupo de função ganha nem perde
nada -- quem já tinha Inventário: Usuário (Logística, gerente comercial)
passa a ver prateleira e a poder fazer transferência interna; quem é
administrador do Inventário ganha também o botão "Realocar" na lista de
estoque, que move várias linhas de uma vez. Visitante e Editorial passam a
ver De/Para nos movimentos que já liam: é o preço de o interruptor ser da
casa inteira, como no Odoo.
""",
    'author': 'EdLab Press',
    'category': 'Inventory',
    'version': '19.0.1.1.0',
    'license': 'AGPL-3',
    'depends': ['stock'],
    'data': [
        'data/res_groups.xml',
        'views/stock_picking_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_stock_shelves/static/src/js/transferencia_interna_tour.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
}
