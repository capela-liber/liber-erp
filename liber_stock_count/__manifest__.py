# -*- coding: utf-8 -*-
{
    'name': "Inventário — a equipe conta, o gerente aplica",
    'summary': "A contagem física é de quem está no depósito; mudar a "
               "quantidade em mãos é só do administrador do Inventário",
    'description': """
No Inventário físico do Odoo 19 há duas colunas: "Em mãos", o que o sistema
acha que existe, e "Contado", o que a pessoa achou na prateleira. Preencher
a segunda é contar. Clicar em "Aplicar" é outra coisa: transforma a
diferença num movimento de ajuste, a quantidade em mãos muda e o livro que
faltava vira perda de inventário.

O core dá os dois gestos ao mesmo grupo: Inventário > Usuário conta E
aplica. Só "Limpar", "Solicitar uma contagem", "Definir como 0" e "Realocar"
são do administrador. O manual dos perfis (liber_roles) prometia outra
coisa -- o Assistente da Logística "faz contagem", o Gerente "valida
ajustes de inventário" -- e a promessa não tinha código atrás.

Este módulo fecha a diferença:

  - na tela do Inventário físico, "Aplicar" (na linha e no cabeçalho) e
    "Aplicar tudo" só aparecem para o administrador do Inventário
    (``stock.group_stock_manager``);
  - no ORM, ``stock.quant._apply_inventory`` -- por onde passa todo ajuste,
    venha da linha, do assistente de motivo, da caixa de conflito, da ficha
    do produto ou do apagar de um quant -- recusa quem não é administrador,
    com AccessError. Menu escondido não fecha RPC nem URL colada; a trava é
    aqui, como nas outras travas da casa;
  - a ficha do produto: escrever "Quantidade em mãos" (``qty_available``)
    cria o quant como superusuário dentro do core, e a trava do quant não
    veria quem escreveu. O inverso é guardado antes, com o usuário de fato.

O que NÃO muda: o Assistente continua contando -- preenche "Contado", usa
"Definir como a quantidade em mãos" quando bate, limpa a própria contagem,
cria linha para o livro que não estava na lista, imprime a Folha de
contagem. Nada do que ele digitou se perde quando a recusa aparece: a
contagem fica gravada na coluna, esperando o gerente. Código com ``sudo()``
passa, como nas outras travas da casa.
""",
    'author': 'EdLab Press',
    'category': 'Inventory',
    'version': '19.0.1.0.0',
    'license': 'AGPL-3',
    'depends': ['stock'],
    'data': [
        'views/stock_quant_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_stock_count/static/src/js/inventario_tour.js',
        ],
    },
    'installable': True,
}
