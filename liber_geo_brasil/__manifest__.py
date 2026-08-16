# -*- coding: utf-8 -*-
{
    'name': 'Liber Geo Brasil (o mapa que a casa usa)',
    'version': '19.0.1.1.0',
    'summary': 'Região "Brasil (UF)" nos gráficos geo, e o card do dashboard por UF',
    'description': """
O mapa-múndi não diz nada para quem vende no Brasil. O card "Top Countries" do
dashboard de Vendas pintava um país inteiro de azul e deixava a pergunta de pé:
*onde*, no Brasil, está o cliente. Este módulo troca o mundo pelas 27 UFs.

São duas peças, e elas são independentes de propósito:

## 1. A região "Brasil (UF)", disponível em qualquer gráfico geo

O `geoJsonService` do core lista as regiões que o gráfico geo oferece (Mundo,
Europa, Estados Unidos...). Aqui ele ganha mais uma, com o desenho das UFs
versionado no módulo -- `static/geojson/brasil_uf.geo.json`, gerado do IBGE por
`scripts/gen_mapa_brasil_uf.py`. A tela nunca fala com o IBGE.

O casamento entre dado e desenho é por sigla: o `feature.id` de cada UF é "SP",
"RJ", "MG", e a etiqueta que vem do Odoo ("São Paulo (BR)") é reduzida à sigla
pelo `res.country.state`. Quem monta um gráfico geo à mão passa a ter o Brasil
na lista de regiões, sem mais nada instalado.

Os anéis saem no sentido **horário**, que é o contrário do que a RFC 7946 pede
e do que o IBGE entrega. É o d3-geo quem manda aqui: para ele um polígono é uma
região da esfera, e um anel na mão errada quer dizer "o planeta inteiro MENOS
este estado". O desenho ainda sai, mas o `fitWidth` passa a emoldurar o mundo e
o Brasil aparece do tamanho que de fato tem nele -- um ponto no meio do card. O
script inverte na geração e o teste guarda.

## 2. O card do dashboard, por UF

A troca acontece na **leitura** do dashboard (`_get_serialized_readonly_dashboard`),
não no dado gravado. A razão é o `spreadsheet_dashboard_sale` do Odoo: o
registro dele não é `noupdate`, então todo upgrade daquele módulo reescreve o
JSON do dashboard e levaria junto qualquer edição nossa. Trocando na leitura, o
dado continua sendo o do Odoo -- e a casa continua vendo o Brasil, na próxima
versão também.

A regra é estreita, para não surpreender: só gráfico do tipo `odoo_geo`,
agrupado exatamente por `country_id`, e só quando o modelo do gráfico tem
`state_id`. Nesse caso ele passa a agrupar por `state_id`, desenhar na região
`br_uf`, e o título do card deixa de dizer "países".

## 3. A aba "Top 10", ao lado do mapa

O card tem duas abas, e a segunda não é gráfico: é uma `carouselDataView`, que
não desenha nada por conta própria -- ela apaga a figura e deixa ver a planilha
que está por baixo. No dashboard de Vendas, o que está por baixo é uma fórmula
`PIVOT` agrupada por país, de um registro que a figura nem menciona. Trocar só o
gráfico deixaria as duas abas do mesmo card discordando uma da outra.

Então o pivô também vira UF, pela mesma regra estreita: uma linha só de
agrupamento, e essa linha é o `country_id`. Junto vão duas coisas que não são
óbvias:

- **o nome do pivô**, porque é ele que a fórmula escreve na célula de canto da
  tabela (`result[0][0]`). Sem isso as UFs apareceriam debaixo de um cabeçalho
  escrito "Country". O nome é nosso, e não o rótulo do campo, porque o
  `state_id` de `sale.report` está traduzido errado no core: em pt_BR ele diz
  "Situação do cliente";
- **a guarda `country_id != False` do domínio**, que vira `state_id != False`.
  Sem isso a tabela traria de volta a linha sem UF -- a que o mapa ao lado não
  tem como desenhar. Um `country_id = <id>` no domínio, esse fica: filtrar por
  um país e agrupar por UF é exatamente o que a casa quer.

**O que isto NÃO faz**: não mexe no dashboard quando ele é *editado* (a edição
abre o dado gravado, que segue o do Odoo), e não converte gráfico nenhum fora de
dashboard. Cliente de fora do Brasil não some do banco -- some do mapa, que é o
que se pediu ao trocar o mundo pelo país.
""",
    'author': 'EdLab Press',
    'category': 'Productivity/Dashboard',
    'depends': ['spreadsheet_dashboard'],
    'assets': {
        'spreadsheet.o_spreadsheet': [
            'liber_geo_brasil/static/src/**/*.js',
        ],
        'web.assets_unit_tests': [
            'liber_geo_brasil/static/tests/**/*',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
