# -*- coding: utf-8 -*-
{
    'name': 'Liber Dashboard Top (os primeiros do gráfico)',
    'version': '19.0.1.0.0',
    'summary': 'Gráfico Odoo com limite de grupos, e o painel Produtos mostrando só os 50 mais vendidos, pelo título',
    'description': """
O painel Produtos (Painéis > Vendas > Produtos) desenha "Melhores vendedores por
receita" com TODO produto vendido no período. Numa editora com centenas de
títulos em giro isso é uma parede de palitos, e a metade direita é ruído: a
cauda de quem vendeu um exemplar. O que se quer ver ali são os primeiros.

São duas peças, e a primeira é genérica de propósito:

## 1. `limit` no gráfico Odoo

O gráfico Odoo do o_spreadsheet (`odoo_bar`, `odoo_line`...) descreve o que
mostra num `metaData` -- modelo, agrupamento, medida, ordem -- e carrega os
dados por um `GraphModel` do web, que não sabe limitar. Aqui a definição ganha
uma chave a mais, `limit`: um inteiro positivo que corta os dados nos N
primeiros grupos do eixo, na ordem em que o `GraphModel` os entregou. Como a
ordem (`order: "DESC"`) é aplicada antes do corte, "os 50 primeiros" são os 50
maiores.

O corte é feito nos PONTOS, antes de virarem séries (`_getProcessedDataPoints`),
e não nas séries prontas. É o que mantém coerente tudo o que sai dali: os
rótulos, cada série de um gráfico empilhado, e o domínio que o clique na barra
usa para abrir a lista. E é o que sobrevive a `updateMetaData`, que reprocessa
os mesmos pontos sem recarregar.

Gráfico sem `limit` fica exatamente como era.

## 2. O painel Produtos, na leitura

A troca acontece na **leitura** do painel (`_get_serialized_readonly_dashboard`),
não no dado gravado, pela razão que o `liber_geo_brasil` e o `liber_soc_moves`
já registram: o registro do `spreadsheet_dashboard_sale` não é `noupdate`, e todo
upgrade do core reescreve o JSON. Na leitura, o dado continua o do Odoo.

A regra é estreita: só gráfico `odoo_bar`, agrupado EXATAMENTE por `product_id`,
e só se ele já vem ordenado -- cortar um gráfico sem ordem mostraria 50
produtos quaisquer, não os 50 primeiros. Quem já tem um `limit` fica com o seu.
Isso pega os dois gráficos do painel Produtos (por receita e por unidades) e
nada mais.

## 3. O título sem o ISBN na frente

O rótulo de cada barra é o `display_name` do produto, que no Odoo é "[código]
nome" -- e o código, na casa, é o ISBN: treze dígitos que não dizem nada num
eixo de gráfico e comem o espaço do título. A mesma leitura põe
`display_default_code: False` no contexto da consulta do gráfico
(`searchParams.context`), que é o que o GraphModel repassa ao `read_group` --
e é o `read_group` quem escreve o rótulo. Dois títulos iguais de ISBN
diferente (uma reedição) o próprio GraphModel separa, com um "(2)" no segundo:
nada some do gráfico. Quem já decidiu sobre a chave, num sentido ou no outro,
fica com a decisão.

O cartão "Mais vendido", no alto, não lê o gráfico: lê um pivô de uma linha
por produto, e o `PIVOT.HEADER` da aba Data escreve o nome que o `read_group`
desse pivô devolveu. A mesma chave entra no `context` do pivô -- de qualquer
pivô de uma linha só, e essa linha o produto, o que alcança também a tabela
"Top Products" do painel Vendas. O pivô continua inteiro, sem corte: o melhor
vendido segue sendo o melhor de todos.

**O que isto NÃO muda**: os cartões "Mais vendido" e "Melhor categoria" no alto
do painel. Eles não leem o gráfico: leem dois pivôs próprios, na aba Data, e
esses seguem inteiros. O melhor vendido continua sendo o melhor de todos.
""",
    'author': 'EdLab Press',
    'category': 'Productivity/Dashboard',
    'depends': ['spreadsheet_dashboard_sale'],
    'assets': {
        # O pacote em que o core carrega a lib e a fonte de dados do gráfico;
        # é dele que os dashboards leem. O `web.assets_unit_tests` já o inclui.
        'spreadsheet.o_spreadsheet': [
            'liber_dashboard_top/static/src/chart_limit.js',
        ],
        'web.assets_unit_tests': [
            'liber_dashboard_top/static/tests/**/*',
        ],
        'web.assets_backend': [
            'liber_dashboard_top/static/src/js/painel_produtos_tour.js',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
