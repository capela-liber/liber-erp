# -*- coding: utf-8 -*-
{
    'name': "Bipagem — transferência entre prateleiras pelo leitor",
    'summary': "Bipe a prateleira, bipe os livros, bipe a prateleira nova: "
               "a transferência interna nasce validada",
    'description': """
A transferência interna pela tela exige escolher a prateleira num
autocompletar de quatrocentos códigos e digitar quantidade. No depósito a
operação natural é com o leitor na mão, na sequência em que o corpo faz:
de onde, o quê, para onde.

A tela "Bipagem" (Inventário > Operações > Bipagem) tem um campo só, sempre
em foco, e três passos ditados pelo que entra nele:

  1. a prateleira de ORIGEM -- a etiqueta da prateleira (EL-000196);
  2. os LIVROS -- um bipe por exemplar, pelo ISBN; o mesmo ISBN de novo
     soma um. Livro que não está naquela prateleira é recusado na hora,
     com o que há dela em cada um;
  3. a prateleira de DESTINO -- e a transferência interna nasce, reserva
     e valida no mesmo bipe. Fica no histórico do livro como qualquer
     outra, numerada na série INT do armazém, com "Bipagem" na origem.

Bipar outra prateleira antes de qualquer livro troca a origem; "desfazer"
tira o último bipe; "recomeçar" limpa tudo. O leitor de mão (USB ou
Bluetooth, modo teclado) funciona em qualquer navegador; o botão "Ler com
a câmera" usa a câmera do celular pela biblioteca ZXing (static/lib), e
exige HTTPS -- no Mac mini passa pelo túnel.

As prateleiras ganham o código de barras na instalação: o próprio código
(EL-000196), que é o que a etiqueta impressa pelo relatório do Odoo
(Inventário > Configuração > Locais > Imprimir > Etiquetas) mostra.
Prateleira criada depois nasce com o código também.

O módulo não inventa regra: a transferência que ele cria passa pelas
mesmas guardas do liber_stock_shelves -- origem e destino são prateleiras
do armazém, nunca a raiz, nunca a prateleira de consignação de um cliente.
""",
    'author': 'EdLab Press',
    'category': 'Inventory',
    'version': '19.0.1.0.1',
    'license': 'AGPL-3',
    'depends': ['liber_stock_shelves'],
    'data': [
        'views/scan_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'liber_stock_scan/static/src/scan/scan.js',
            'liber_stock_scan/static/src/scan/scan.xml',
            'liber_stock_scan/static/src/scan/scan.scss',
            'liber_stock_scan/static/src/js/bipagem_tour.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
}
