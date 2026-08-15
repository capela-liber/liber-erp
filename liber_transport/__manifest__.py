# -*- coding: utf-8 -*-
{
    'name': "Transport — transportadora e coleta",
    'summary': "A transportadora do cliente chega ao movimento, e a coleta sai por e-mail",
    'description': """
O começo do transporte: quem leva, e quando vem buscar.

O Odoo já sabe metade da história: o cadastro do cliente tem o campo "Método
de entrega" (a Catavento usa a Transpo), e a transferência tem o campo
transportadora. Mas o método de entrega nativo é só um nome com preço — não é
uma empresa, não tem e-mail, e nada liga o campo do cliente ao movimento que a
logística vê. Este módulo fecha essas pontas:

  - o método de entrega ganha a empresa transportadora (um contato normal,
    com e-mail, CNPJ e telefone) — é para ela que a coleta é pedida;
  - a transferência de saída nasce já com a transportadora do cliente,
    sem depender do passo de frete da venda;
  - a lista de transferências ganha a ação "Solicitar coleta": seleciona os
    movimentos e sai UM e-mail por transportadora com a lista das entregas
    (referência, pedido, destinatário, cidade/UF) — catorze entregas da
    Transpo são um pedido de coleta, não catorze;
  - cada pedido vira um LOTE numerado (COL/ano/00001) com histórico
    próprio: o e-mail fica lá, a resposta da transportadora volta para lá,
    e o estado acompanha até a carga sair (Rascunho, Enviada, Coletada).
    Mora em Inventário > Operações > Transferências > Solicitações de
    coleta;
  - o texto de abertura do e-mail é editável nas Definições (bloco
    Transporte), por empresa; o histórico de cada movimento registra o
    pedido com link para o lote, e a lista ganha os filtros "Com coleta
    solicitada" / "Sem coleta";
  - a transferência ganha a contagem de CAIXAS: quem embala digita, e o
    número segue para dois lugares — a nota fiscal, que precisa declarar
    volumes e peso, e o e-mail da coleta, por onde a transportadora escolhe
    o veículo. Peso e caixas aparecem por entrega e somados no lote;
  - o menu Imprimir da lista ganha "Picking": seleciona as entregas e sai um
    PDF que começa por UMA folha com tudo somado por título, na ordem da
    prateleira — quem coleta faz um passeio só, em vez de um por pedido —, e
    segue com a folha de cada entrega para conferir e embalar. Todas as
    linhas têm quadradinho de conferência, e o peso dos livros sai por linha
    e somado, com o seu quadradinho, para bater na balança antes de fechar a
    caixa. Uma entrega só na seleção não ganha a folha do passeio: seria a
    cópia da folha do pedido;
  - cálculo de frete fica para a próxima etapa — as regras de preço nativas
    do método de entrega já dão a base.

A prateleira da folha não é campo novo: é o local de origem da linha do
movimento, que a migração endereçou (``EL-000137``) e a reserva escolhe. Por
isso a quantidade que manda ali é a reservada — e o que não foi reservado NÃO
vira linha de coleta: linha com quadradinho é ordem de buscar, e mandar buscar
o que o sistema não separou ou não acha nada na prateleira, ou embala
exemplar que não está na entrega. A folha só avisa, numa linha, que a entrega
está incompleta; resolver isso é de quem prepara, antes de o papel ir para a
bancada.
""",
    'author': 'EdLab Press',
    'category': 'Inventory',
    'version': '19.0.2.4.0',
    'license': 'AGPL-3',
    'depends': ['stock_delivery', 'sale_stock'],
    'data': [
        'security/ir.model.access.csv',
        'security/liber_transport_security.xml',
        'data/ir_sequence.xml',
        'data/mail_templates.xml',
        'views/pickup_request_views.xml',
        'views/delivery_carrier_views.xml',
        'views/stock_picking_views.xml',
        'views/pickup_request_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'report/report_picking_sheet.xml',
    ],
    'installable': True,
}
