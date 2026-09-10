# -*- coding: utf-8 -*-
"""O gráfico de produtos do painel ganha o limite e perde o ISBN na leitura."""

import json

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.liber_dashboard_top.models.spreadsheet_dashboard import (
    CAMPO_PRODUTO, CHAVE_CODIGO, CHAVE_LIMITE, TIPO_BARRAS, TOP,
)

DOMINIO = [['state', 'not in', ['draft', 'sent', 'cancel']]]


def grafico(tipo=TIPO_BARRAS, agrupamento=None, ordem='DESC', contexto=None, **meta_extra):
    """Um gráfico Odoo do painel Produtos, no essencial."""
    agrupamento = [CAMPO_PRODUTO] if agrupamento is None else agrupamento
    meta = {'groupBy': agrupamento, 'measure': 'price_subtotal',
            'order': ordem, 'resModel': 'sale.report', 'mode': 'bar'}
    meta.update(meta_extra)
    return {'type': tipo, 'metaData': meta,
            'searchParams': {'domain': DOMINIO, 'groupBy': agrupamento,
                             'context': {'group_by': []} if contexto is None else contexto,
                             'orderBy': []}}


def figura(definicao, id_='g1'):
    return {'id': id_, 'tag': 'chart', 'data': definicao}


def carrossel(*definicoes):
    return {'id': 'c1', 'tag': 'carousel', 'data': {
        'chartDefinitions': {str(i): d for i, d in enumerate(definicoes)},
        'items': [{'type': 'chart', 'chartId': str(i)} for i in range(len(definicoes))],
    }}


def pivo(linhas=None, contexto=None, id_='1'):
    """O pivô "Product" do painel Produtos, no essencial: é ele que o cartão lê."""
    linhas = [{'fieldName': CAMPO_PRODUTO}] if linhas is None else linhas
    return {id_: {
        'type': 'ODOO', 'id': id_, 'formulaId': id_, 'name': 'Product',
        'model': 'sale.report', 'rows': linhas, 'columns': [],
        'measures': [{'id': 'product_uom_qty', 'fieldName': 'product_uom_qty'}],
        'domain': DOMINIO, 'context': {'group_by': []} if contexto is None else contexto,
        'sortedColumn': {'measure': 'product_uom_qty', 'order': 'desc', 'domain': []},
    }}


def planilha(*figuras, pivos=None):
    snapshot = {'sheets': [{'figures': list(figuras)}]}
    if pivos is not None:
        snapshot['pivots'] = pivos
    return snapshot


@tagged('post_install', '-at_install')
class TestTopNoPainel(TransactionCase):

    def setUp(self):
        super().setUp()
        self.dashboard = self.env['spreadsheet.dashboard'].search([], limit=1)
        if not self.dashboard:
            self.skipTest("nenhum spreadsheet.dashboard neste banco")

    def _ler(self, snapshot):
        """Passa uma planilha pelo caminho de leitura e devolve o que sai."""
        self.dashboard.spreadsheet_data = json.dumps(snapshot)
        return json.loads(self.dashboard._get_serialized_readonly_dashboard())['snapshot']

    def _grafico(self, lido, indice=0):
        return lido['sheets'][0]['figures'][indice]['data']

    def _meta(self, lido, indice=0):
        return self._grafico(lido, indice)['metaData']

    def _contexto(self, lido, indice=0):
        return self._grafico(lido, indice)['searchParams']['context']

    # ------------------------------------------------------------ caminho feliz
    def test_barras_por_produto_ganham_o_limite(self):
        lido = self._ler(planilha(figura(grafico())))
        self.assertEqual(self._meta(lido)[CHAVE_LIMITE], TOP)

    def test_o_isbn_sai_do_rotulo(self):
        """O contexto da consulta pede o produto sem o código. O resto fica."""
        lido = self._ler(planilha(figura(grafico())))
        self.assertEqual(self._contexto(lido), {'group_by': [], CHAVE_CODIGO: False})

    def test_os_dois_graficos_do_painel(self):
        """Receita e unidades: os dois são barras por produto, os dois mudam."""
        lido = self._ler(planilha(figura(grafico(measure='price_subtotal'), 'g1'),
                                  figura(grafico(measure='product_uom_qty'), 'g2')))
        for indice in (0, 1):
            self.assertEqual(self._meta(lido, indice)[CHAVE_LIMITE], TOP)
            self.assertFalse(self._contexto(lido, indice)[CHAVE_CODIGO])

    def test_dentro_de_um_carrossel_tambem(self):
        lido = self._ler(planilha(carrossel(grafico(), grafico(tipo='odoo_pie'))))
        definicoes = lido['sheets'][0]['figures'][0]['data']['chartDefinitions']
        self.assertEqual(definicoes['0']['metaData'][CHAVE_LIMITE], TOP)
        self.assertFalse(definicoes['0']['searchParams']['context'][CHAVE_CODIGO])
        self.assertNotIn(CHAVE_LIMITE, definicoes['1']['metaData'])
        self.assertNotIn(CHAVE_CODIGO, definicoes['1']['searchParams']['context'])

    def test_o_dado_gravado_nao_muda(self):
        """A troca é de leitura: quem editar o painel vê o dado do Odoo."""
        self._ler(planilha(figura(grafico())))
        gravado = self._grafico(json.loads(self.dashboard.spreadsheet_data))
        self.assertNotIn(CHAVE_LIMITE, gravado['metaData'])
        self.assertNotIn(CHAVE_CODIGO, gravado['searchParams']['context'])

    def test_a_leitura_e_idempotente(self):
        uma_vez = self._ler(planilha(figura(grafico())))
        duas_vezes = self._ler(uma_vez)
        self.assertEqual(duas_vezes, uma_vez)

    def test_o_cartao_mais_vendido_tambem_perde_o_isbn(self):
        """O cartão lê um pivô por produto, e o pivô carrega o próprio contexto."""
        lido = self._ler(planilha(pivos=pivo()))
        self.assertEqual(lido['pivots']['1']['context'], {'group_by': [], CHAVE_CODIGO: False})
        gravado = json.loads(self.dashboard.spreadsheet_data)
        self.assertNotIn(CHAVE_CODIGO, gravado['pivots']['1']['context'])

    def test_pivo_que_nao_e_o_do_cartao_fica_intacto(self):
        """Por categoria, por produto e mês, sem linha: nenhum é "o do cartão"."""
        for linhas in ([{'fieldName': 'categ_id'}],
                       [{'fieldName': CAMPO_PRODUTO}, {'fieldName': 'date', 'granularity': 'month'}],
                       []):
            lido = self._ler(planilha(pivos=pivo(linhas=linhas)))
            self.assertNotIn(CHAVE_CODIGO, lido['pivots']['1']['context'], linhas)

    def test_pivo_que_ja_decidiu_fica_com_a_decisao(self):
        lido = self._ler(planilha(pivos=pivo(contexto={CHAVE_CODIGO: True})))
        self.assertTrue(lido['pivots']['1']['context'][CHAVE_CODIGO])

    def test_pivo_torto_nao_estoura(self):
        for torto in (None, 'nada disso', {'rows': None}, {'rows': 'torto'},
                      {'rows': ['torto']}, {'rows': [{'fieldName': CAMPO_PRODUTO}],
                                            'context': 'torto'}):
            self.assertFalse(self.dashboard._ajustar_pivo(torto), torto)
        self.assertFalse(self.dashboard._ajustar_pivos({'pivots': 'torto'}))

    # ------------------------------------------------------------------ arestas
    def test_sem_ordem_nao_ha_primeiros(self):
        """Cortar um gráfico sem ordem mostraria 50 produtos quaisquer.

        O nome sem código não depende de ordem, e esse sai mesmo assim.
        """
        for ordem in (None, ''):
            lido = self._ler(planilha(figura(grafico(ordem=ordem))))
            self.assertNotIn(CHAVE_LIMITE, self._meta(lido), ordem)
            self.assertFalse(self._contexto(lido)[CHAVE_CODIGO], ordem)

    def test_quem_ja_decidiu_fica_com_a_decisao(self):
        lido = self._ler(planilha(figura(grafico(limit=10, contexto={CHAVE_CODIGO: True}))))
        self.assertEqual(self._meta(lido)[CHAVE_LIMITE], 10)
        self.assertTrue(self._contexto(lido)[CHAVE_CODIGO])

    def test_grafico_sem_contexto_ganha_um(self):
        lido = self._ler(planilha(figura(grafico(contexto={}))))
        self.assertEqual(self._contexto(lido), {CHAVE_CODIGO: False})

    def test_outro_agrupamento_fica_intacto(self):
        """Categoria, cliente, produto-e-mês: nenhum é "o gráfico de produtos"."""
        for agrupamento in (['categ_id'], ['partner_id'], [CAMPO_PRODUTO, 'date:month'], []):
            lido = self._ler(planilha(figura(grafico(agrupamento=agrupamento))))
            self.assertNotIn(CHAVE_LIMITE, self._meta(lido), agrupamento)
            self.assertNotIn(CHAVE_CODIGO, self._contexto(lido), agrupamento)

    def test_outro_tipo_de_grafico_fica_intacto(self):
        for tipo in ('odoo_pie', 'odoo_line', 'odoo_treemap', 'bar', 'scorecard'):
            lido = self._ler(planilha(figura(grafico(tipo=tipo))))
            self.assertNotIn(CHAVE_LIMITE, self._meta(lido), tipo)
            self.assertNotIn(CHAVE_CODIGO, self._contexto(lido), tipo)

    def test_planilha_torta_nao_estoura(self):
        """O caso de erro: o JSON vem de fora, e errar derrubaria o painel todo."""
        for torta in ({}, {'sheets': None}, {'sheets': ['nada disso']},
                      {'sheets': [{'figures': None}]},
                      {'sheets': [{'figures': ['nada disso']}]},
                      {'sheets': [{'figures': [{'data': 'torto'}]}]},
                      {'sheets': [{'figures': [{'data': {'chartDefinitions': 'torto'}}]}]},
                      {'sheets': [{'figures': [{'data': {'type': TIPO_BARRAS,
                                                         'metaData': 'torto'}}]}]}):
            self.assertFalse(self.dashboard._ajustar_planilha(torta), torta)
        self.assertFalse(self.dashboard._ajustar_planilha('nada disso'))

    def test_grafico_com_a_consulta_torta_ainda_ganha_o_limite(self):
        """`searchParams` que não é dicionário: o código fica, o limite entra.

        Aqui o método é chamado direto, e não pelo `_ler`: o core valida a
        planilha ao gravá-la (`_check_spreadsheet_data` lê
        `searchParams["groupBy"]`), então esta forma torta nem chega a ser
        gravada. O que se guarda é que, se chegar por outro caminho, as duas
        trocas são independentes -- uma quebrada não leva a outra.
        """
        for params in (None, 'torto', {'context': 'torto'}):
            definicao = grafico()
            definicao['searchParams'] = params
            self.assertTrue(self.dashboard._ajustar_grafico(definicao), params)
            self.assertEqual(definicao['metaData'][CHAVE_LIMITE], TOP, params)

    # -------------------------------------------------------------- integração
    def test_o_painel_produtos_de_verdade(self):
        """O registro do core, como o leitor o recebe: os dois gráficos ajustados."""
        painel = self.env.ref('spreadsheet_dashboard_sale.spreadsheet_dashboard_product')
        snapshot = json.loads(painel._get_serialized_readonly_dashboard())['snapshot']
        barras = [f['data'] for aba in snapshot['sheets'] for f in aba.get('figures', [])
                  if f.get('data', {}).get('type') == TIPO_BARRAS]
        self.assertEqual(len(barras), 2, "o painel Produtos deveria ter dois gráficos de barras")
        for definicao in barras:
            self.assertEqual(definicao['metaData']['groupBy'], [CAMPO_PRODUTO])
            self.assertEqual(definicao['metaData'][CHAVE_LIMITE], TOP)
            self.assertFalse(definicao['searchParams']['context'][CHAVE_CODIGO])

    def test_os_cartoes_do_alto_continuam_lendo_tudo(self):
        """"Mais vendido" e "Melhor categoria" leem pivôs próprios, inteiros.

        O limite é do gráfico; o pivô do cartão segue sem corte, sobre todos os
        produtos. A única coisa que muda nele é o contexto que tira o ISBN -- e
        só no pivô por produto, que é o que o cartão da esquerda lê.
        """
        painel = self.env.ref('spreadsheet_dashboard_sale.spreadsheet_dashboard_product')
        gravado = json.loads(painel.spreadsheet_data)['pivots']
        lido = json.loads(painel._get_serialized_readonly_dashboard())['snapshot']['pivots']
        self.assertTrue(gravado, "o painel Produtos deveria ter pivôs")
        por_produto = [k for k, p in gravado.items()
                       if p['rows'] == [{'fieldName': CAMPO_PRODUTO}]]
        self.assertEqual(len(por_produto), 1)
        for chave, original in gravado.items():
            servido = dict(lido[chave])
            contexto = dict(servido.pop('context'))
            self.assertEqual(servido, {k: v for k, v in original.items() if k != 'context'})
            if chave in por_produto:
                self.assertFalse(contexto.pop(CHAVE_CODIGO))
            self.assertEqual(contexto, original['context'])

    def test_o_rotulo_que_a_consulta_devolve(self):
        """O que o gráfico vai escrever no eixo, com o contexto servido.

        O `read_group` de `sale.report` agrupado por produto devolve
        `[id, display_name]`, e é esse nome que vira rótulo. Com o contexto do
        painel gravado ele vem "[ISBN] título"; com o contexto servido, só o
        título.
        """
        livraria = self.env['res.partner'].create({'name': 'Livraria do Rótulo'})
        livro = self.env['product.product'].create({
            'name': 'Livro do Rótulo', 'default_code': '9786500000001',
            'type': 'consu', 'list_price': 30.0})
        pedido = self.env['sale.order'].create({
            'partner_id': livraria.id,
            'order_line': [(0, 0, {'product_id': livro.id, 'product_uom_qty': 2})],
        })
        pedido.action_confirm()
        painel = self.env.ref('spreadsheet_dashboard_sale.spreadsheet_dashboard_product')
        servido = json.loads(painel._get_serialized_readonly_dashboard())['snapshot']
        contexto = next(f['data']['searchParams']['context']
                        for aba in servido['sheets'] for f in aba.get('figures', [])
                        if f.get('data', {}).get('type') == TIPO_BARRAS)

        def rotulo(contexto):
            grupos = self.env['sale.report'].with_context(**contexto).formatted_read_group(
                [('product_id', '=', livro.id)], ['product_id'], ['price_subtotal:sum'])
            return grupos[0]['product_id'][1]

        self.assertEqual(rotulo({}), '[9786500000001] Livro do Rótulo')
        self.assertEqual(rotulo(contexto), 'Livro do Rótulo')
