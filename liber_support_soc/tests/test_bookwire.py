# -*- coding: utf-8 -*-
"""O relatório da Bookwire vira pedido de venda pelo chamado.

A Bookwire manda todo mês um ZIP com um CSV nativo. Até 27/09/2026 a casa
lançava só a fatura, digitada à mão, e o digital ficava fora de Vendas >
Relatórios. Estes testes travam o que torna esse pedido diferente da venda
comum: o preço é o líquido do relatório (não o de capa, nem a lista do
cliente), o total fecha ao centavo, a faixa de streaming não conta como
exemplar, e o pedido nasce na empresa da editora.
"""
import base64
import io
import zipfile

from odoo.exceptions import UserError
from odoo.tests import common, tagged
from odoo.tools.misc import file_path

from ..models import bookwire_report

EDITORA = 'Editora do Tour'          # o CSV diz "Editora do Tour LTDA"
TOTAL = 27.06


def csv_exemplo():
    with open(file_path(
            'liber_support_soc/tests/fixtures/bookwire_exemplo.csv'),
            'rb') as f:
        return f.read()


def zip_exemplo():
    """O anexo como a Bookwire manda: o CSV dentro do ZIP, ao lado do PDF."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('2026-0801-0831 - A-1 - Editora do Tour LTDA.csv',
                    csv_exemplo())
        zf.writestr('2026-0801-0831 - A-1 - Editora do Tour LTDA.pdf',
                    b'%PDF-1.4 relatorio')
    return buf.getvalue()


def semear(env):
    """Cliente, produtos digitais, equipe e chamado com o ZIP anexado.

    Compartilhado com o tour (`test_tour_bookwire.py`)."""
    env.company.name = EDITORA
    env.ref('base.group_user').implied_ids += (
        env.ref('product.group_product_pricelist')
        + env.ref('sale.group_discount_per_so_line'))
    # A lista de 55% está aqui de propósito: é o desconto que um contato da
    # casa costuma ter, e o pedido do relatório tem de passar por cima dele.
    lista = env['product.pricelist'].create({
        'name': '55% bookwire teste',
        'item_ids': [(0, 0, {'applied_on': '3_global',
                             'compute_price': 'percentage',
                             'percent_price': 55.0})],
    })
    bookwire = env['res.partner'].create({
        'name': 'Bookwire do Tour', 'is_company': True})
    bookwire.specific_property_product_pricelist = lista
    digital = env['crm.team'].create({'name': 'Digital do Tour'})
    if 'team_id' in bookwire._fields:
        bookwire.with_company(env.company).team_id = digital
    produtos = env['product.product']
    for isbn, nome in (('9780000000019', 'Ebook do Tour'),
                       ('9780000000026', 'Audiolivro do Tour'),
                       ('9780000000033', 'Ebook Devolvido')):
        produtos |= env['product.product'].create({
            'name': nome, 'type': 'service', 'sale_ok': True,
            'barcode': isbn, 'list_price': 49.90})
    equipe = env['liber.support.team'].create({
        'name': 'Atendimento Bookwire', 'company_id': env.company.id,
        'alias_name': 'bookwire-tour-test'})
    chamado = env['liber.support.ticket'].create({
        'name': 'Fwd: Bookwire - Sales Report - 8/2026',
        'team_id': equipe.id, 'partner_id': bookwire.id})
    env['ir.attachment'].create({
        'name': '2026-0801-0831 - A-1 - Editora do Tour LTDA.zip',
        'res_model': chamado._name, 'res_id': chamado.id,
        'datas': base64.b64encode(zip_exemplo())})
    return {'bookwire': bookwire, 'digital': digital, 'produtos': produtos,
            'equipe': equipe, 'chamado': chamado}


@tagged('post_install', '-at_install')
class TestRelatorioBookwire(common.TransactionCase):
    """A leitura, sem banco: formato, agrupamento e centavos."""

    def test_le_o_csv_dentro_do_zip(self):
        texto = bookwire_report.ler('relatorio.zip', zip_exemplo())
        relatorio = bookwire_report.interpretar(texto)
        self.assertEqual(relatorio['periodo'], '08/2026')
        self.assertEqual(relatorio['editora'], 'Editora do Tour LTDA')

    def test_total_fecha_ao_centavo(self):
        """R$ 6,67 por 2 unidades não tem preço unitário de 2 casas."""
        relatorio = bookwire_report.interpretar(
            bookwire_report.ler('r.csv', csv_exemplo()))
        linhas = bookwire_report.linhas_do_pedido(relatorio['titulos'])
        self.assertAlmostEqual(
            sum(l['qty'] * l['preco'] for l in linhas), TOTAL, places=2)
        ebook = [l for l in linhas if l['isbn'] == '9780000000019']
        self.assertEqual([(l['qty'], l['preco']) for l in ebook],
                         [(1, 3.33), (1, 3.34)])

    def test_faixa_de_streaming_e_uma_unidade(self):
        relatorio = bookwire_report.interpretar(
            bookwire_report.ler('r.csv', csv_exemplo()))
        faixa = [l for l in bookwire_report.linhas_do_pedido(
            relatorio['titulos']) if l['nota']]
        self.assertEqual(len(faixa), 1)
        self.assertEqual((faixa[0]['qty'], faixa[0]['preco']), (1, 0.39))
        self.assertIn('62', faixa[0]['nota'])

    def test_titulo_devolvido_inteiro_nao_vira_linha(self):
        relatorio = bookwire_report.interpretar(
            bookwire_report.ler('r.csv', csv_exemplo()))
        isbns = {l['isbn'] for l in bookwire_report.linhas_do_pedido(
            relatorio['titulos'])}
        self.assertNotIn('9780000000033', isbns)

    def test_divisao_exata_e_uma_linha_so(self):
        linhas = bookwire_report.linhas_do_pedido([{
            'isbn': '1', 'titulo': 'x', 'faixa': False,
            'unidades': 4, 'centavos': 1000}])
        self.assertEqual([(l['qty'], l['preco']) for l in linhas], [(4, 2.5)])

    def test_nao_e_relatorio_devolve_none(self):
        self.assertIsNone(bookwire_report.ler('pedido.csv', b'titulo;qtd\nA;3'))
        self.assertIsNone(bookwire_report.ler('relatorio.xlsx', csv_exemplo()))
        self.assertIsNone(bookwire_report.ler('quebrado.zip', b'PK\x03\x04lixo'))


@tagged('post_install', '-at_install')
class TestPedidoDoRelatorio(common.TransactionCase):
    """Do chamado ao pedido, pelo assistente."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dados = semear(cls.env)
        cls.chamado = cls.dados['chamado']
        cls.Wizard = cls.env['liber.support.co.wizard']

    def _assistente(self):
        self.Wizard._open_for(self.chamado)
        return self.Wizard.search([('ticket_id', '=', self.chamado.id)])

    def test_assistente_reconhece_o_relatorio(self):
        wizard = self._assistente()
        self.assertEqual(wizard.report_period, '08/2026')
        self.assertEqual(wizard.default_dest, 'sale')
        self.assertEqual(wizard.report_company_id, self.env.company)
        self.assertEqual(len(wizard.line_ids), 4)
        self.assertTrue(all(wizard.line_ids.mapped('product_id')))

    def test_pedido_soma_o_relatorio_e_ignora_a_lista(self):
        wizard = self._assistente()
        wizard.action_create_co()
        pedido = self.chamado.sale_order_id
        self.assertTrue(pedido, 'não criou o pedido')
        self.assertAlmostEqual(pedido.amount_untaxed, TOTAL, places=2)
        self.assertEqual(set(pedido.order_line.mapped('discount')), {0.0},
                         'a lista de 55% do cliente entrou no pedido')
        self.assertEqual(pedido.client_order_ref, 'Period:08/2026')
        self.assertEqual(pedido.company_id, self.env.company)
        if 'team_id' in self.dados['bookwire']._fields:
            self.assertEqual(pedido.team_id, self.dados['digital'])
        faixa = pedido.order_line.filtered(
            lambda l: 'Audiotrack' in (l.name or ''))
        self.assertEqual(faixa.product_uom_qty, 1)

    def test_pedido_confirmado_nao_abre_entrega(self):
        wizard = self._assistente()
        wizard.action_create_co()
        pedido = self.chamado.sale_order_id
        pedido.action_confirm()
        if 'picking_ids' in pedido._fields:
            self.assertFalse(pedido.picking_ids)
        self.assertEqual(pedido.invoice_status, 'to invoice')

    def test_editora_desconhecida_fica_na_empresa_do_chamado(self):
        self.assertFalse(self.Wizard._report_company('Outra Editora S.A.'))
        self.assertEqual(self.Wizard._report_company('EDITORA DO TOUR Ltda.'),
                         self.env.company)

    def test_isbn_sem_produto_recusa_o_pedido(self):
        """Linha sem produto sumiria, e o pedido não somaria o relatório."""
        self.dados['produtos'].filtered(
            lambda p: p.barcode == '9780000000026').barcode = '9780000000999'
        wizard = self._assistente()
        with self.assertRaises(UserError):
            wizard.action_create_co()
        self.assertFalse(self.chamado.sale_order_id)

    def test_chamado_sem_cliente_ganha_a_bookwire(self):
        """O e-mail chega encaminhado de dentro da casa, sem cliente."""
        self.chamado.partner_id = False
        wizard = self._assistente()
        self.assertEqual(wizard.partner_id, self.dados['bookwire'])
        self.assertEqual(self.chamado.partner_id, self.dados['bookwire'])

    def test_isbn_na_referencia_interna_tambem_casa(self):
        ebook = self.dados['produtos'].filtered(
            lambda p: p.barcode == '9780000000019')
        ebook.write({'barcode': False, 'default_code': '9780000000019'})
        wizard = self._assistente()
        self.assertEqual(
            wizard.line_ids.filtered(
                lambda l: l.label_source.startswith('9780000000019')
            ).product_id, ebook)

    def test_ebook_ainda_mercadoria_avisa_e_nao_bloqueia(self):
        ebook = self.dados['produtos'].filtered(
            lambda p: p.barcode == '9780000000019')
        ebook.write({'type': 'consu', 'is_storable': True})
        wizard = self._assistente()
        self.assertTrue(wizard.report_alert)
        self.assertEqual(
            set(wizard.line_ids.filtered(
                lambda l: l.product_id == ebook).mapped('confidence')),
            {'weak'})
        wizard.action_create_co()
        self.assertTrue(self.chamado.sale_order_id)

    def test_salvar_com_linha_virtual_nao_quebra(self):
        """O que o staging recebeu em 27/09/2026 (chamado 2129): duas
        releituras seguidas na tela, e o salvamento mandando apagar uma linha
        que nunca foi ao banco. Quebrava com `virtual_602`."""
        wizard = self._assistente()
        antes = len(wizard.line_ids)
        wizard.write({'line_ids': [
            (2, 'virtual_602'),
            (1, 'virtual_603', {'qty': 9}),
            (0, 0, {'label_source': 'nova', 'qty': 1}),
        ]})
        self.assertEqual(len(wizard.line_ids), antes + 1)

    def test_pela_tela_o_relatorio_sobrevive_ao_salvar(self):
        """Escolher o ZIP pela tela e salvar: o assistente não pode esquecer
        que é o relatório -- sem `force_save` o pedido saía a preço de capa."""
        from odoo.tests import Form
        zip_ = self.env['ir.attachment'].search(
            [('res_model', '=', self.chamado._name),
             ('res_id', '=', self.chamado.id)], limit=1)
        outro = self.env['ir.attachment'].create({
            'name': 'convertido.csv', 'res_model': self.chamado._name,
            'res_id': self.chamado.id, 'raw': b'2;Ebook do Tour\n'})
        wizard = self._assistente()
        wizard.attachment_id = outro
        wizard.action_parse()
        self.assertFalse(wizard.report_period)
        with Form(wizard) as f:
            f.attachment_id = zip_
        self.assertEqual(wizard.report_period, '08/2026')
        self.assertTrue(all(wizard.line_ids.mapped('label_source')))
        wizard.action_create_co()
        self.assertAlmostEqual(
            self.chamado.sale_order_id.amount_untaxed, TOTAL, places=2)
