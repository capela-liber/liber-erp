# -*- coding: utf-8 -*-
{
    'name': "Fairs — nota de simples remessa",
    'summary': "A carga da feira sai com nota: remessa para exposição ou feira, emitida para nós mesmos",
    'description': """
A nota que acompanha a carga da feira.

Livro na estrada sem nota é livro apreendido. A remessa para uma feira não é
venda e não pode sair na série de venda: ela é uma **simples remessa**, com
CFOP de remessa para exposição ou feira (5.914 dentro do estado, 6.914 fora),
e o destinatário **é a própria editora** — a mercadoria não muda de dono ao
subir na van, muda de lugar.

O que este módulo faz:

  - põe o botão **Gerar nota de remessa** na feira. Ele emite uma nota por
    transferência de remessa já concluída, no diário de remessas REM-F, sob a
    posição fiscal de feira configurada nas Definições;
  - a nota nasce **baixada**: o `liber_nfe_remessa` reconcilia a perna de
    recebível contra a conta que a posição fiscal declara, e por isso a
    editora nunca fica devendo a si mesma;
  - carimba a transferência com a nota, e a nota com a feira, para que cada
    carga na estrada tenha o seu documento e nenhuma seja declarada duas
    vezes;
  - declara a quantidade **efetivamente despachada**, nunca a planejada. Uma
    nota que diz 100 quando saíram 62 não bate com o volume na estrada, e é
    a nota que o fiscal lê.

Por que é um módulo separado: uma feira é remessa temporária, e isso vale em
qualquer país. O módulo `liber_fairs` não pode exigir a nota fiscal brasileira
para existir. Quem tem NF-e instala esta ponte, e ela aparece sozinha.

A NOTA DA VOLTA sai no mesmo clique do Retorno, e é nota de crédito: a ida e
a volta se anulam, que é exatamente o que aconteceu — a mercadoria saiu e
voltou, e nada mudou de dono no caminho. Ela referencia a chave da nota de
ida, sob a posição fiscal de retorno (CFOP 1.914 / 2.914).

Uma diferença entre as duas que parece inconsistência e não é. A nota de IDA
declara o que foi efetivamente despachado, porque ela sai depois de o armazém
separar, e é ali que se sabe o que entrou na van. A nota da VOLTA declara o
que está sendo devolvido, porque ela sai quando as caixas deixam a feira: ela
viaja COM elas. Nota que só saísse na chegada deixaria o caminhão rodar sem
documento.

A diferença entre o que a nota da volta declara e o que o armazém recebe é
assunto da conferência do retorno, em Recebimentos: o que não aparece na
caixa vira perda "Não voltou (a explicar)". É onde essa conversa tem de
acontecer, e não escondida numa nota que ninguém emitiu.
""",
    'author': 'EdLab Press',
    'category': 'Inventory',
    'version': '19.0.1.6.0',
    'license': 'AGPL-3',
    'depends': ['liber_fairs', 'liber_nfe_remessa'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/event_fair_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'application': False,
}
