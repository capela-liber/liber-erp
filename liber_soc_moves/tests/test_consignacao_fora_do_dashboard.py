# -*- coding: utf-8 -*-
"""A consignação sai também das tabelas do dashboard de Vendas.

Os cards e os gráficos do dashboard leem `sale.report`, e ali o Pedido C já não
entra: o `sale_report.py` tira a consignação na cláusula WHERE do relatório. As
duas tabelas do pé da página -- "Cotações por valor sem impostos" e "Pedidos
por valor sem impostos" -- não são pivô: são LISTA, e lista lê `sale.order`
direto. O dashboard dizia em cima que consignação não é venda e contava
consignação embaixo.

A troca é de LEITURA, e é isso que estes testes guardam junto com o domínio: o
registro do `spreadsheet_dashboard_sale` não é `noupdate`, e um upgrade do core
apagaria uma edição gravada.
"""
import json

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.liber_soc_moves.models.spreadsheet_dashboard import (
    GUARD, SALE_ORDER,
)

# O domínio das duas listas do dashboard de Vendas, como estão no
# `sales_dashboard.json` do core: uma pega a cotação viva, a outra o pedido.
DOMINIO_COTACOES = ['|', ['state', '=', 'draft'], ['state', '=', 'sent']]
DOMINIO_PEDIDOS = [['state', 'not in', ['draft', 'sent', 'cancel']]]


def lista(model=SALE_ORDER, dominio=None):
    """Uma lista do dashboard, no essencial."""
    return {'1': {
        'id': '1',
        'name': 'Sales Orders by Untaxed Amount',
        'model': model,
        'columns': ['name', 'partner_id', 'amount_untaxed'],
        'domain': DOMINIO_PEDIDOS if dominio is None else dominio,
        'context': {},
        'orderBy': [],
    }}


def pivo(model='sale.report', dominio=None):
    return {'3': {
        'type': 'ODOO',
        'id': '3',
        'formulaId': '3',
        'name': 'Customer',
        'model': model,
        'rows': [{'fieldName': 'partner_id'}],
        'columns': [],
        'measures': [{'id': 'price_subtotal', 'fieldName': 'price_subtotal'}],
        'domain': DOMINIO_PEDIDOS if dominio is None else dominio,
        'context': {},
    }}


def grafico(model=SALE_ORDER, dominio=None):
    """Uma figura de gráfico: o modelo no `metaData`, o domínio no `searchParams`."""
    return {'sheets': [{'figures': [{'id': 'g1', 'tag': 'chart', 'data': {
        'type': 'odoo_line',
        'metaData': {'groupBy': ['date_order:month'], 'measure': 'amount_untaxed',
                     'resModel': model, 'mode': 'line'},
        'searchParams': {'domain': DOMINIO_PEDIDOS if dominio is None else dominio,
                         'groupBy': ['date_order:month'], 'context': {}, 'orderBy': []},
    }}]}]}


def planilha(listas=None, pivos=None, folhas=None):
    return {'sheets': (folhas or {}).get('sheets', [{'figures': []}]),
            'lists': listas or {},
            'pivots': pivos or {}}


@tagged('post_install', '-at_install')
class TestConsignacaoForaDoDashboard(TransactionCase):

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
    def test_a_lista_de_pedidos_ganha_a_guarda(self):
        lido = self._ler(planilha(listas=lista()))
        self.assertIn(GUARD, lido['lists']['1']['domain'])

    def test_o_dominio_servido_e_um_dominio_de_verdade(self):
        """A prosódia do domínio: prefixo, e um "&" por operando acrescentado.

        Somar guarda a um domínio em notação prefixa é onde se erra em
        silêncio -- o dashboard não reclama, ele traz o número errado. Quem
        confere é o ORM: domínio torto estoura na busca.
        """
        for original in ([], DOMINIO_PEDIDOS, DOMINIO_COTACOES):
            lido = self._ler(planilha(listas=lista(dominio=original)))
            servido = lido['lists']['1']['domain']
            self.env['sale.order'].search(servido, limit=1)

    def test_o_filtro_do_dashboard_continua_de_pe(self):
        """A guarda entra ao lado do `state`, não no lugar dele.

        Sem o `state` a tabela de cotações passaria a listar pedido confirmado
        e cancelado -- trocaria um número errado por outro.
        """
        lido = self._ler(planilha(listas=lista(dominio=DOMINIO_COTACOES)))
        dominio = lido['lists']['1']['domain']
        self.assertIn(GUARD, dominio)
        for termo in DOMINIO_COTACOES:
            self.assertIn(termo, dominio)

    def test_o_c_sai_e_o_s_do_acerto_fica(self):
        """O que a tabela passa a listar, na prática.

        O S é o documento que o Acerto cria (`_create_sale_order`), e ele nasce
        sem a marca de propósito: é ELE a venda, é nele que a consignação vira
        receita. Sai o Pedido C, que é remessa.
        """
        parceiro = self.env['res.partner'].create({'name': 'Livraria do Painel'})
        produto = self.env['product.product'].create({
            'name': 'Livro do Painel', 'type': 'consu', 'list_price': 30.0})
        def pedido(consignacao):
            return self.env['sale.order'].create({
                'partner_id': parceiro.id,
                'is_consignment': consignacao,
                'order_line': [(0, 0, {'product_id': produto.id,
                                       'product_uom_qty': 2})],
            })
        remessa, venda = pedido(True), pedido(False)
        lido = self._ler(planilha(listas=lista(dominio=[])))
        achados = self.env['sale.order'].search(lido['lists']['1']['domain'])
        self.assertIn(venda, achados)
        self.assertNotIn(remessa, achados)

    def test_o_grafico_de_pedidos_tambem(self):
        """Gráfico nenhum do core lê `sale.order` hoje -- mas se ler, é a mesma regra."""
        lido = self._ler(planilha(folhas=grafico()))
        figura = lido['sheets'][0]['figures'][0]['data']
        self.assertIn(GUARD, figura['searchParams']['domain'])

    def test_o_dado_gravado_nao_muda(self):
        """A troca é de leitura: quem editar o dashboard vê o dado do Odoo."""
        self._ler(planilha(listas=lista()))
        gravado = json.loads(self.dashboard.spreadsheet_data)
        self.assertEqual(gravado['lists']['1']['domain'], DOMINIO_PEDIDOS)

    # ------------------------------------------------------------------ arestas
    def test_o_pivo_de_sale_report_fica_intacto(self):
        """Ali a consignação já não entra: quem a tira é a WHERE do relatório.

        Repetir a guarda no domínio filtraria por um campo que o `sale.report`
        nem tem, e o pivô quebraria.
        """
        lido = self._ler(planilha(pivos=pivo()))
        self.assertEqual(lido['pivots']['3']['domain'], DOMINIO_PEDIDOS)

    def test_lista_sem_dominio_ganha_so_a_guarda(self):
        """Domínio vazio: entra a guarda, e sem "&" sobrando na frente."""
        guardas = self.dashboard._sale_order_dashboard_guards()
        lido = self._ler(planilha(listas=lista(dominio=[])))
        self.assertEqual(lido['lists']['1']['domain'],
                         ['&'] * (len(guardas) - 1) + guardas)

    def test_a_guarda_nao_entra_duas_vezes(self):
        """Idempotente: o dashboard passa pela leitura a cada abertura."""
        uma_vez = self._ler(planilha(listas=lista()))
        duas_vezes = self._ler(uma_vez)
        self.assertEqual(duas_vezes['lists']['1']['domain'],
                         uma_vez['lists']['1']['domain'])

    def test_dominio_em_texto_fica_intacto(self):
        """A fronteira declarada: domínio gravado como string não é mexido.

        O o_spreadsheet grava assim o domínio de alguns gráficos. Nenhum deles
        lê `sale.order` no core, e reescrever domínio a partir de texto seria
        promessa maior do que esta.
        """
        texto = '[("state", "!=", "cancel")]'
        self.assertFalse(self.dashboard._guard_sale_order_source(
            {'model': SALE_ORDER, 'domain': texto}, [GUARD]))

    def test_planilha_torta_nao_estoura(self):
        """O caso de erro: o JSON vem de fora, e errar derrubaria o dashboard todo."""
        for torta in ({}, {'lists': None, 'pivots': None, 'sheets': None},
                      {'lists': {'1': 'nada disso'}},
                      {'sheets': ['nada disso']},
                      {'sheets': [{'figures': ['nada disso']}]},
                      {'sheets': [{'figures': [{'data': {'metaData': 'torto'}}]}]},
                      {'sheets': [{'figures': [{'data': {
                          'metaData': {'resModel': SALE_ORDER}}}]}]}):
            self.assertEqual(list(self.dashboard._sale_order_sources(torta)), [],
                             torta)
        for torto in (None, 'nada disso', {'domain': 42}):
            self.assertFalse(
                self.dashboard._guard_sale_order_source(torto, [GUARD]), torto)

    # -------------------------------------------------------------- integração
    def test_o_dashboard_de_vendas_de_verdade(self):
        """O registro do core, como o leitor o recebe: as duas listas com a guarda."""
        vendas = self.env.ref('spreadsheet_dashboard_sale.spreadsheet_dashboard_sales',
                              raise_if_not_found=False)
        if not vendas:
            self.skipTest("`spreadsheet_dashboard_sale` não está instalado")
        snapshot = json.loads(vendas._get_serialized_readonly_dashboard())['snapshot']
        listas = [fonte for fonte in snapshot['lists'].values()
                  if fonte.get('model') == SALE_ORDER]
        self.assertTrue(listas, "o dashboard de Vendas não tem lista de `sale.order`")
        for fonte in listas:
            self.assertIn(GUARD, fonte['domain'], fonte.get('name'))
