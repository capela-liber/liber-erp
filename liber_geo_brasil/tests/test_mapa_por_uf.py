# -*- coding: utf-8 -*-
"""O mapa do dashboard sai por UF -- e o dado gravado continua o do Odoo."""

import json

from odoo.tests.common import TransactionCase, tagged
from odoo.tools import file_open

from odoo.addons.liber_geo_brasil.models.spreadsheet_dashboard import (
    CAMPO_PAIS, CAMPO_UF, REGIAO_BR, TITULO, TITULO_PIVO,
)

MAPA = 'liber_geo_brasil/static/geojson/brasil_uf.geo.json'


def area_com_sinal(anel):
    """Área do anel pela fórmula do cadarço. Positiva = anti-horário."""
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(anel, anel[1:])) / 2


def aneis(geometria):
    """Os anéis da geometria, o externo primeiro em cada polígono."""
    coordenadas = geometria['coordinates']
    poligonos = [coordenadas] if geometria['type'] == 'Polygon' else coordenadas
    return [(indice, anel) for poligono in poligonos
            for indice, anel in enumerate(poligono)]


def planilha(*figuras, pivos=None):
    snapshot = {'sheets': [{'figures': list(figuras)}]}
    if pivos is not None:
        snapshot['pivots'] = pivos
    return snapshot


def pivo_de_paises(model='sale.report', measure='price_subtotal', linhas=None, dominio=None):
    """O pivô "Country" do dashboard de Vendas, no essencial.

    É ele que a aba "Top 10" mostra. A `carouselDataView` do carrossel não
    desenha nada por conta própria: ela apaga a figura e deixa ver a planilha
    por baixo, onde mora uma fórmula `PIVOT` que a figura nem menciona.
    """
    if linhas is None:
        linhas = [{'fieldName': CAMPO_PAIS}]
    if dominio is None:
        dominio = ['&', [CAMPO_PAIS, '!=', False],
                   ['state', 'not in', ['draft', 'sent', 'cancel']]]
    return {'5': {
        'type': 'ODOO',
        'id': '5',
        'formulaId': '5',
        # O nome é o que a fórmula escreve na célula de canto da tabela.
        'name': 'Country',
        'model': model,
        'rows': linhas,
        'columns': [],
        'measures': [{'id': measure, 'fieldName': measure, 'userDefinedName': 'Revenue'}],
        'domain': dominio,
        'context': {},
    }}


def carrossel_de_paises(res_model='sale.report', measure='price_subtotal'):
    """O card "Top Countries" do dashboard de Vendas, no essencial."""
    return {
        'id': 'figura-1',
        'tag': 'carousel',
        'data': {
            'title': {'text': 'Top Countries'},
            'chartDefinitions': {
                'abc': {
                    'type': 'odoo_geo',
                    'metaData': {'groupBy': ['country_id'], 'resModel': res_model,
                                 'measure': measure},
                    'searchParams': {'groupBy': ['country_id'], 'domain': '[]'},
                },
            },
            'items': [{'type': 'chart', 'chartId': 'abc'}, {'type': 'carouselDataView'}],
        },
    }


@tagged('post_install', '-at_install')
class TestMapaPorUf(TransactionCase):

    def setUp(self):
        super().setUp()
        self.dashboard = self.env['spreadsheet.dashboard'].search([], limit=1)
        if not self.dashboard:
            self.skipTest("nenhum spreadsheet.dashboard neste banco")

    def _ler(self, snapshot):
        """Passa uma planilha pelo caminho de leitura e devolve o que sai."""
        self.dashboard.spreadsheet_data = json.dumps(snapshot)
        return json.loads(self.dashboard._get_serialized_readonly_dashboard())['snapshot']

    # ------------------------------------------------------------ caminho feliz
    def test_mapa_mundi_por_pais_vira_brasil_por_uf(self):
        lido = self._ler(planilha(carrossel_de_paises()))
        figura = lido['sheets'][0]['figures'][0]
        grafico = figura['data']['chartDefinitions']['abc']
        self.assertEqual(grafico['region'], REGIAO_BR)
        self.assertEqual(grafico['metaData']['groupBy'], ['state_id'])
        self.assertEqual(grafico['searchParams']['groupBy'], ['state_id'])
        self.assertEqual(figura['data']['title']['text'], TITULO)

    def test_o_dado_gravado_nao_muda(self):
        """A troca é de leitura. Quem editar o dashboard vê o dado do Odoo."""
        original = planilha(carrossel_de_paises())
        self._ler(original)
        gravado = json.loads(self.dashboard.spreadsheet_data)
        grafico = gravado['sheets'][0]['figures'][0]['data']['chartDefinitions']['abc']
        self.assertEqual(grafico['metaData']['groupBy'], ['country_id'])
        self.assertNotIn('region', grafico)

    # ------------------------------------------------------------------ arestas
    def test_modelo_sem_uf_fica_intacto(self):
        """Modelo que sabe o país mas não a UF: mexer ali seria inventar.

        `res.country.state` tem `country_id` (senão a planilha nem grava: em
        modo de teste o Odoo confere se o campo existe no modelo) e não tem
        `state_id`, que é exatamente o caso a cobrir.
        """
        lido = self._ler(planilha(
            carrossel_de_paises(res_model='res.country.state', measure='id')))
        figura = lido['sheets'][0]['figures'][0]
        self.assertEqual(
            figura['data']['chartDefinitions']['abc']['metaData']['groupBy'], ['country_id'])
        self.assertEqual(figura['data']['title']['text'], 'Top Countries')

    def test_grafico_que_nao_e_geo_fica_intacto(self):
        grafico = {'id': 'figura-1', 'tag': 'chart', 'data': {
            'type': 'odoo_line', 'title': {'text': 'Vendas'},
            'metaData': {'groupBy': ['country_id'], 'resModel': 'sale.report',
                         'measure': 'price_subtotal'},
            'searchParams': {'groupBy': ['country_id'], 'domain': '[]'}}}
        lido = self._ler(planilha(grafico))
        self.assertEqual(lido['sheets'][0]['figures'][0]['data']['type'], 'odoo_line')
        self.assertEqual(lido['sheets'][0]['figures'][0]['data']['title']['text'], 'Vendas')

    def test_geo_agrupado_por_outra_coisa_fica_intacto(self):
        """Mapa-múndi montado de propósito com outro agrupamento não é nosso."""
        figura = carrossel_de_paises()
        figura['data']['chartDefinitions']['abc']['metaData']['groupBy'] = ['partner_id']
        lido = self._ler(planilha(figura))
        grafico = lido['sheets'][0]['figures'][0]['data']['chartDefinitions']['abc']
        self.assertNotIn('region', grafico)

    def test_planilha_vazia_nao_estoura(self):
        """O caso de erro: dashboard sem aba, sem figura, sem nada."""
        lido = self._ler({})
        self.assertNotIn('sheets', lido)

    # --------------------------------------------------- a tabela do "Top 10"
    def test_pivo_de_paises_vira_pivo_de_ufs(self):
        lido = self._ler(planilha(pivos=pivo_de_paises()))
        pivo = lido['pivots']['5']
        self.assertEqual(pivo['rows'], [{'fieldName': CAMPO_UF}])

    def test_o_cabecalho_da_tabela_deixa_de_dizer_pais(self):
        """A célula de canto da tabela é o NOME do pivô, não o rótulo do campo.

        A fórmula `PIVOT` escreve `getPivotName(...)` em `result[0][0]` sempre
        que houver linha de cabeçalho -- por isso a tabela do Odoo diz
        "Country", e não "País do cliente". Trocar a linha e esquecer o nome
        listaria as UFs debaixo de um cabeçalho escrito "Country", que é o
        erro que este teste existe para pegar.
        """
        lido = self._ler(planilha(pivos=pivo_de_paises()))
        self.assertEqual(lido['pivots']['5']['name'], TITULO_PIVO)

    def test_a_guarda_de_pais_vira_guarda_de_uf(self):
        """`country_id != False` traria de volta a linha que o mapa não desenha."""
        lido = self._ler(planilha(pivos=pivo_de_paises()))
        self.assertEqual(lido['pivots']['5']['domain'], [
            '&', [CAMPO_UF, '!=', False],
            ['state', 'not in', ['draft', 'sent', 'cancel']],
        ])

    def test_filtro_por_um_pais_sobrevive(self):
        """Filtrar por Brasil e agrupar por UF é exatamente o que a casa quer.

        Só a guarda "tem país" é que sai. Um `country_id = <id>` no domínio é
        escolha de quem montou, e reescrevê-lo mudaria o que a tabela conta.
        """
        dominio = [[CAMPO_PAIS, '=', 31], ['state', '!=', 'cancel']]
        lido = self._ler(planilha(pivos=pivo_de_paises(dominio=dominio)))
        self.assertEqual(lido['pivots']['5']['domain'], dominio)

    def test_o_pivo_gravado_nao_muda(self):
        """A troca do pivô também é de leitura, como a do gráfico."""
        self._ler(planilha(pivos=pivo_de_paises()))
        gravado = json.loads(self.dashboard.spreadsheet_data)
        self.assertEqual(gravado['pivots']['5']['rows'], [{'fieldName': CAMPO_PAIS}])
        self.assertEqual(gravado['pivots']['5']['name'], 'Country')

    # ------------------------------------------------------------------ arestas
    def test_pivo_de_dois_niveis_fica_intacto(self):
        """País mais alguma coisa é outra pergunta, e não é a nossa."""
        linhas = [{'fieldName': CAMPO_PAIS}, {'fieldName': 'product_id'}]
        lido = self._ler(planilha(pivos=pivo_de_paises(linhas=linhas)))
        self.assertEqual(lido['pivots']['5']['rows'], linhas)
        self.assertEqual(lido['pivots']['5']['name'], 'Country')

    def test_pivo_de_outro_agrupamento_fica_intacto(self):
        linhas = [{'fieldName': 'product_id'}]
        lido = self._ler(planilha(pivos=pivo_de_paises(linhas=linhas)))
        self.assertEqual(lido['pivots']['5']['rows'], linhas)

    def test_pivo_de_modelo_sem_uf_fica_intacto(self):
        """`res.country.state` sabe o país e não tem `state_id`.

        O domínio vai sem o `state`, que é campo do `sale.report`: o Odoo
        valida os campos da planilha na gravação e recusaria o registro antes
        de o nosso código ver o pivô.
        """
        lido = self._ler(planilha(pivos=pivo_de_paises(
            model='res.country.state', measure='id',
            dominio=[[CAMPO_PAIS, '!=', False]])))
        self.assertEqual(lido['pivots']['5']['rows'], [{'fieldName': CAMPO_PAIS}])

    def test_pivo_malformado_nao_estoura(self):
        """O caso de erro: pivô sem linhas, ou com linha que não é dicionário.

        Aqui a chamada é direta, e não pela gravação: o `_check_spreadsheet_data`
        do Odoo recusa uma planilha com pivô torto, então este dado não entra
        por escrita nenhuma. A guarda existe porque o JSON vem de fora e o
        preço de errar seria derrubar a leitura do dashboard inteiro.
        """
        for torto in (None, 'nada disso', {'type': 'ODOO', 'model': 'sale.report'},
                      {'model': 'sale.report', 'rows': []},
                      {'model': 'sale.report', 'rows': [CAMPO_PAIS]},
                      {'model': 'sale.report', 'rows': [{'fieldName': CAMPO_PAIS}] * 2}):
            self.assertFalse(self.dashboard._brasilizar_pivo(torto), torto)

    # -------------------------------------------------------- o mapa e o banco
    def test_o_mapa_casa_com_as_ufs_do_banco(self):
        """Desenho e dado têm de falar a mesma língua: a sigla.

        Se o mapa trouxer uma sigla que o `res.country.state` não tem (ou o
        contrário), aquela UF fica cinza na tela sem nenhum erro aparecer.
        """
        with file_open(MAPA, 'r') as arquivo:
            mapa = json.load(arquivo)
        do_mapa = {feature['id'] for feature in mapa['features']}
        self.assertEqual(len(mapa['features']), 27, "o Brasil tem 27 UFs")
        do_banco = set(self.env['res.country.state'].search(
            [('country_id.code', '=', 'BR')]).mapped('code'))
        self.assertEqual(do_mapa, do_banco)

    def test_os_aneis_estao_na_mao_do_d3(self):
        """Anel externo no sentido horário, buraco ao contrário.

        A RFC 7946 pede o oposto e o IBGE entrega assim -- por isso o
        `gen_mapa_brasil_uf.py` inverte antes de gravar. O d3-geo, que desenha
        por baixo do `chartjs-chart-geo`, lê polígono como região da esfera:
        anel na mão errada quer dizer "o planeta inteiro MENOS este estado".

        O desenho ainda sai; quem quebra é o enquadramento. O `fitWidth` do
        `ProjectionScale` passa a emoldurar o mundo, e o Brasil aparece do
        tamanho que de fato tem nele -- um ponto no meio do card. Foi o que
        houve na primeira versão deste mapa, e é o que este teste guarda.
        """
        with file_open(MAPA, 'r') as arquivo:
            mapa = json.load(arquivo)
        for feature in mapa['features']:
            for indice, anel in aneis(feature['geometry']):
                horario = area_com_sinal(anel) < 0
                self.assertEqual(
                    horario, indice == 0,
                    f"{feature['id']}: anel {indice} está na mão errada para o d3")
