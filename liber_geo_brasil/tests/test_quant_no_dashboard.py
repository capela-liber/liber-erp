# -*- coding: utf-8 -*-
"""A coluna "Orders" das tabelas "Top ..." sai como quantidade vendida."""

import json

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.liber_geo_brasil.models.spreadsheet_dashboard import (
    CAMPO_QUANTIDADE, CAMPO_UF, MEDIDA_PEDIDOS, ROTULO_PEDIDOS, ROTULO_QUANT,
)

# A medida que o leitor tem de ver no lugar da contagem: a soma da quantidade,
# com o cabeçalho "Quant" no `userDefinedName` -- que é o que a fórmula
# `PIVOT(...)` escreve na célula de cabeçalho da coluna.
MEDIDA_QUANT = {'id': CAMPO_QUANTIDADE, 'fieldName': CAMPO_QUANTIDADE,
                'aggregator': 'sum', 'userDefinedName': ROTULO_QUANT}


def medida_de_pedidos():
    """A medida de contagem do core, como está no `sales_dashboard.json`.

    Não é `__count`: o dashboard de Vendas conta o `order_reference` (a
    referência ao pedido), e o cabeçalho "Orders" mora no `userDefinedName`.
    """
    return {'id': MEDIDA_PEDIDOS, 'fieldName': MEDIDA_PEDIDOS,
            'userDefinedName': ROTULO_PEDIDOS}


def medida_de_receita():
    return {'id': 'price_subtotal', 'fieldName': 'price_subtotal',
            'userDefinedName': 'Revenue'}


def pivo_top(model='sale.report', medidas=None, linhas=None):
    """Um pivô "Top ..." do dashboard de Vendas, no essencial.

    É o formato dos pivôs "Product", "Customer", "Sales Team", "Salesperson":
    uma linha de agrupamento e as medidas Orders + Revenue. A tabela sai de
    uma fórmula `PIVOT(6, 10, FALSE, FALSE)` inteira -- célula nenhuma
    menciona uma medida pelo nome, ao contrário dos pivôs de estatística.
    """
    if medidas is None:
        medidas = [medida_de_pedidos(), medida_de_receita()]
    if linhas is None:
        linhas = [{'fieldName': 'product_id'}]
    return {'6': {
        'type': 'ODOO',
        'id': '6',
        'formulaId': '6',
        'name': 'Product',
        'model': model,
        'rows': linhas,
        'columns': [],
        'measures': medidas,
        'domain': [],
        'context': {},
    }}


def planilha(pivos):
    return {'sheets': [{'figures': []}], 'pivots': pivos}


@tagged('post_install', '-at_install')
class TestQuantNoDashboard(TransactionCase):

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
    def test_a_contagem_de_pedidos_vira_quantidade(self):
        """"Orders" sai, e no lugar entra a soma de `product_uom_qty`."""
        lido = self._ler(planilha(pivo_top()))
        self.assertEqual(lido['pivots']['6']['measures'][0], MEDIDA_QUANT)

    def test_o_cabecalho_da_coluna_diz_quant(self):
        lido = self._ler(planilha(pivo_top()))
        self.assertEqual(
            lido['pivots']['6']['measures'][0]['userDefinedName'], ROTULO_QUANT)

    def test_a_receita_fica_como_esta(self):
        """A troca é da contagem, e SÓ dela. O Revenue não é da nossa conta."""
        lido = self._ler(planilha(pivo_top()))
        medidas = lido['pivots']['6']['measures']
        self.assertEqual(len(medidas), 2)
        self.assertEqual(medidas[1], medida_de_receita())

    def test_o_pivo_gravado_nao_muda(self):
        """A troca é de leitura. Quem editar o dashboard vê o dado do Odoo."""
        self._ler(planilha(pivo_top()))
        gravado = json.loads(self.dashboard.spreadsheet_data)
        self.assertEqual(gravado['pivots']['6']['measures'],
                         [medida_de_pedidos(), medida_de_receita()])

    def test_a_uf_e_a_quantidade_saem_juntas_do_pivo_de_paises(self):
        """O pivô "Country" real leva as duas trocas: a linha e a medida."""
        lido = self._ler(planilha(pivo_top(linhas=[{'fieldName': 'country_id'}])))
        pivo = lido['pivots']['6']
        self.assertEqual(pivo['rows'], [{'fieldName': CAMPO_UF}])
        self.assertEqual(pivo['measures'][0], MEDIDA_QUANT)

    # ------------------------------------------------------------------ arestas
    def test_medida_sem_cabecalho_fica_intacta(self):
        """Os pivôs "so stats" contam pedidos SEM `userDefinedName`.

        E as células os leem por fórmula -- `PIVOT.VALUE(11, "order_reference",
        "state", "sale")` -- que quebraria se a medida mudasse de identidade.
        Este teste guarda a fronteira: contagem sem o cabeçalho "Orders" não é
        tabela "Top ...", e não é nossa.
        """
        medidas = [{'id': MEDIDA_PEDIDOS, 'fieldName': MEDIDA_PEDIDOS},
                   {'id': 'price_subtotal', 'fieldName': 'price_subtotal'}]
        lido = self._ler(planilha(pivo_top(
            medidas=medidas, linhas=[{'fieldName': 'state'}])))
        self.assertEqual(lido['pivots']['6']['measures'], medidas)

    def test_pivo_sem_a_medida_de_contagem_fica_intacto(self):
        lido = self._ler(planilha(pivo_top(medidas=[medida_de_receita()])))
        self.assertEqual(lido['pivots']['6']['measures'], [medida_de_receita()])

    def test_pivo_que_ja_soma_a_quantidade_fica_intacto(self):
        """Quem pôs "Orders" E a quantidade quis as duas colunas.

        Trocar a contagem criaria uma medida `product_uom_qty` duplicada -- e
        apagaria uma coluna que alguém escolheu ter.
        """
        medidas = [medida_de_pedidos(),
                   {'id': CAMPO_QUANTIDADE, 'fieldName': CAMPO_QUANTIDADE,
                    'userDefinedName': 'Qty'}]
        lido = self._ler(planilha(pivo_top(medidas=medidas)))
        self.assertEqual(lido['pivots']['6']['measures'], medidas)

    def test_pivo_de_outro_modelo_fica_intacto(self):
        """Modelo sem `product_uom_qty` não tem o que somar: mexer seria inventar.

        A chamada é direta porque este dado não entra por escrita: o Odoo
        valida os campos da planilha na gravação, e `res.partner` não tem
        `order_reference` para a medida apontar.
        """
        pivo = pivo_top(model='res.partner')['6']
        self.assertFalse(self.dashboard._quantificar_pivo(pivo))
        self.assertEqual(pivo['measures'][0], medida_de_pedidos())

    def test_pivo_malformado_nao_estoura(self):
        """O caso de erro: pivô sem medidas, medida torta, contagem em dobro.

        Como no teste do mapa, a chamada é direta: o `_check_spreadsheet_data`
        do Odoo recusaria estes dados na gravação. A guarda existe porque o
        JSON vem de fora e o preço de errar seria derrubar a leitura do
        dashboard inteiro.
        """
        for torto in (None, 'nada disso',
                      {'model': 'sale.report'},
                      {'model': 'sale.report', 'measures': 'Orders'},
                      {'model': 'sale.report', 'measures': [MEDIDA_PEDIDOS]},
                      {'model': 'sale.report',
                       'measures': [medida_de_pedidos(), medida_de_pedidos()]}):
            self.assertFalse(self.dashboard._quantificar_pivo(torto), torto)
