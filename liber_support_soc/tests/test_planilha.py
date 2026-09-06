# -*- coding: utf-8 -*-
"""A leitura de planilha do assistente, com arquivos de verdade.

Os testes antigos alimentavam o parser com listas Python já prontas e
por isso saíam verdes enquanto a tela não lia nada. Aqui cada caso ABRE
um arquivo — .xlsx montado na hora, .xls OLE do fixture, SpreadsheetML,
HTML e CSV — porque o defeito morava justamente entre o arquivo e as
listas.

O gabarito veio do censo de 01/09/2026 sobre os 84 anexos de planilha
dos chamados: 61% eram .xls OLE (que estourava exceção), 17% eram XML
ou HTML com a extensão .xls, e só 23% eram .xlsx.
"""
import io
import os

from odoo.tests import common, tagged

from ..models import co_parser


def _xlsx(rows, sheets=None):
    """Linhas -> bytes de um .xlsx de verdade. `sheets` monta mais de uma
    aba: [(nome, linhas), ...]."""
    import openpyxl
    book = openpyxl.Workbook()
    pages = sheets or [('Pedido', rows)]
    book.remove(book.active)
    for name, page in pages:
        sheet = book.create_sheet(name)
        for row in page:
            sheet.append(list(row))
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


@tagged('post_install', '-at_install')
class TestPlanilha(common.TransactionCase):
    """Funções puras do co_parser — sem ORM, como manda o CLAUDE.md."""

    def _items(self, name, raw):
        return co_parser.parse_lines(co_parser.sheet_to_text(name, raw))

    # -- caminho feliz -------------------------------------------------

    def test_xlsx_com_cabecalho(self):
        raw = _xlsx([
            ('ISBN', 'Título', 'Qtde'),
            ('9788577151234', 'Banguela', 2),
            ('9786589705468', 'Fim do SUS?', 3),
        ])
        items = self._items('pedido.xlsx', raw)
        self.assertEqual([(i['qty'], i['isbn']) for i in items],
                         [(2, '9788577151234'), (3, '9786589705468')])
        self.assertEqual(items[0]['label'], 'Banguela')

    def test_cabecalho_nao_vira_item(self):
        raw = _xlsx([('ISBN', 'Título', 'Qtde'),
                     ('9788577151234', 'Banguela', 2)])
        self.assertEqual(len(self._items('p.xlsx', raw)), 1)

    # -- os defeitos que os arquivos reais revelaram --------------------

    def test_quantidade_nao_sai_da_coluna_de_estoque(self):
        """O 97202.xlsx importava ZERO em tudo: a regra posicional pegava
        o primeiro número depois do ISBN, que era `estoque`."""
        raw = _xlsx([
            ('ean', 'produto', 'estoque', 'consignado', 'sugestao',
             'unitario', 'desconto'),
            ('9786581295301', 'Meu avô Samantha', 0, 1, 4, 53, 40),
        ])
        items = self._items('sugestao.xlsx', raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['qty'], 4, "leu estoque/desconto no "
                                             "lugar da coluna sugestão")

    def test_dados_na_segunda_aba(self):
        """A planilha-padrão de metadados abre com a aba de instruções;
        ler só worksheets[0] devolvia a bula (92418.xlsx)."""
        raw = _xlsx(None, sheets=[
            ('(1) Instruções', [('Preencha na aba ao lado',)]),
            ('(2) Metadados', [('ISBN', 'Título', 'Quantidade'),
                               ('9788577151234', 'Banguela', 5)]),
        ])
        items = self._items('metadados.xlsx', raw)
        self.assertEqual([(i['qty'], i['isbn']) for i in items],
                         [(5, '9788577151234')])

    def test_isbn_com_hifen(self):
        raw = _xlsx([('ISBN', 'Título', 'Qtd'),
                     ('978-85-7715-123-4', 'Banguela', 2)])
        self.assertEqual(self._items('h.xlsx', raw)[0]['isbn'],
                         '9788577151234')

    def test_linha_com_isbn_nao_e_descartada_como_conversa(self):
        """A linha do produto da planilha do FNDE carrega o endereço do
        órgão e sumia inteira no filtro de ruído (97431.xlsx)."""
        raw = _xlsx([
            ('ISBN', 'Título', 'Qtde', 'Dados do órgão'),
            ('9786589829119', 'Minuano e a pena', 6,
             'SBS Quadra 2, CEP 70070-929, Brasília, DF'),
        ])
        items = self._items('fnde.xlsx', raw)
        self.assertEqual([(i['qty'], i['isbn']) for i in items],
                         [(6, '9786589829119')])

    def test_rotulo_numerico_nao_vira_quantidade(self):
        """Coluna 'Ítem' com 0001, 0002... era relida como quantidade
        quando o texto canônico voltava ao parser (97607.xls)."""
        items = co_parser.parse_lines(
            '0001\t9786551590115\t10\n0002\t9786589705253\t4')
        self.assertEqual([i['qty'] for i in items], [10, 4])

    def test_titulo_ganha_de_item_como_rotulo(self):
        raw = _xlsx([('Ítem', 'Título', 'Cod. Barras', 'Qtd.'),
                     ('0001', 'Alba', '9786551590115', 10)])
        item = self._items('r.xlsx', raw)[0]
        self.assertEqual((item['qty'], item['label']), (10, 'Alba'))

    def test_cabecalho_da_empresa_nao_vence_o_da_tabela(self):
        """'Pedido de Consignação Nº 5.802' casava duas palavras do
        vocabulário e vinha antes do cabeçalho real (96315.xls)."""
        raw = _xlsx([
            ('BUSSOLA DISTRIBUIDORA', 'Pedido de Consignação Nº 5.802',
             'isbn correto'),
            ('ISBN', 'TÍtulo', 'Qtd', 'Vlr Unitário', 'Desc'),
            ('9786584716193', 'Vitor Ramil', 5, 89.9, 52),
        ])
        items = self._items('bussola.xlsx', raw)
        self.assertEqual([(i['qty'], i['isbn']) for i in items],
                         [(5, '9786584716193')])

    def test_planilha_sem_cabecalho_so_da_linha_com_isbn(self):
        """Relatório sem cabeçalho reconhecível não pode transformar
        'PÁG.: 1' e 'DADOS GERAIS' em itens."""
        raw = _xlsx([('Relatório de pendências',),
                     ('PÁG.: 1', 'DADOS GERAIS'),
                     ('Banguela', '9788577151234', 2)])
        items = self._items('rel.xlsx', raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['isbn'], '9788577151234')

    # -- os outros formatos que chegam com a extensão .xls --------------

    def test_xls_ole_do_excel_antigo(self):
        """Era 61% dos anexos e o único formato que estourava exceção:
        o binário ia para o csv.reader e morria em 'new-line character
        seen in unquoted field'. O fixture tem duas abas, ISBN com
        hífen, coluna de estoque zerada e desconto — tudo junto."""
        path = os.path.join(os.path.dirname(__file__), 'fixtures',
                            'pedido_excel_antigo.xls')
        with open(path, 'rb') as handle:
            raw = handle.read()
        items = self._items('pedido.xls', raw)
        self.assertEqual([(i['qty'], i['isbn'], i['label']) for i in items],
                         [(7, '9788577151234', 'Banguela'),
                          (3, '9786589705468', 'Fim do SUS?')])

    def test_spreadsheetml_com_extensao_xls(self):
        """XML do Excel 2003. Virava centenas de linhas de lixo, todas
        com quantidade 1."""
        raw = ('<?xml version="1.0"?>'
               '<?mso-application progid="Excel.Sheet"?>'
               '<Workbook xmlns="urn:schemas-microsoft-com:office:'
               'spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:'
               'spreadsheet"><Worksheet ss:Name="Pedido"><Table>'
               '<Row><Cell><Data>ISBN</Data></Cell>'
               '<Cell><Data>Título</Data></Cell>'
               '<Cell><Data>Qtd</Data></Cell></Row>'
               '<Row><Cell><Data>9788577151234</Data></Cell>'
               '<Cell><Data>Banguela</Data></Cell>'
               '<Cell><Data>9</Data></Cell></Row>'
               '</Table></Worksheet></Workbook>').encode('utf-8')
        self.assertTrue(co_parser.is_spreadsheetml(raw))
        items = self._items('pedido.xls', raw)
        self.assertEqual([(i['qty'], i['isbn']) for i in items],
                         [(9, '9788577151234')])

    def test_spreadsheetml_respeita_celula_pulada(self):
        """O ss:Index é como o formato representa coluna vazia; ignorá-lo
        desalinha a linha e joga o valor na coluna errada."""
        raw = ('<?xml version="1.0"?><Workbook xmlns="urn:schemas-'
               'microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-'
               'microsoft-com:office:spreadsheet"><Worksheet><Table>'
               '<Row><Cell><Data>a</Data></Cell>'
               '<Cell ss:Index="4"><Data>d</Data></Cell></Row>'
               '</Table></Worksheet></Workbook>').encode('utf-8')
        self.assertEqual(co_parser.sheet_pages('x.xls', raw),
                         [[['a', '', '', 'd']]])

    def test_html_com_extensao_xls(self):
        """O sistema da livraria exporta relatório em HTML e salva com
        nome de planilha (22351.xls)."""
        raw = ('﻿<div><table>'
               '<tr><th>ISBN</th><th>Título</th><th>Qtd</th></tr>'
               '<tr><td>9788577151234</td><td>Banguela</td><td>4</td></tr>'
               '</table></div>').encode('utf-8')
        self.assertTrue(co_parser.is_html_table(raw))
        items = self._items('relatorio.xls', raw)
        self.assertEqual([(i['qty'], i['isbn']) for i in items],
                         [(4, '9788577151234')])

    def test_csv_com_ponto_e_virgula_dentro_do_titulo(self):
        """O delimitador saía de `';' in text`: um ponto e vírgula no
        título fazia o arquivo, separado por vírgula, virar coluna só."""
        raw = ('ISBN,Título,Qtd\n'
               '9788577151234,"Fim do SUS?; e agora",6\n').encode('utf-8')
        items = self._items('pedido.csv', raw)
        self.assertEqual([(i['qty'], i['isbn']) for i in items],
                         [(6, '9788577151234')])

    def test_formato_vem_da_assinatura_e_nao_da_extensao(self):
        """Metade dos anexos reais chega com a extensão errada."""
        raw = _xlsx([('ISBN', 'Título', 'Qtd'),
                     ('9788577151234', 'Banguela', 2)])
        semextensao = self._items('planilha', raw)
        comextensaoerrada = self._items('planilha.xls', raw)
        self.assertEqual(len(semextensao), 1)
        self.assertEqual(semextensao, comextensaoerrada)

    # -- erro ----------------------------------------------------------

    def test_arquivo_corrompido_nao_derruba_o_assistente(self):
        """Antes o erro subia do onchange e o operador ficava sem o
        texto do e-mail também."""
        wizard = self.env['liber.support.co.wizard']
        quebrado = b'PK\x03\x04nada disso e um zip de verdade'
        self.assertEqual(wizard._spreadsheet_to_text('x.xlsx', quebrado), '')

    def test_planilha_vazia_nao_da_item(self):
        self.assertEqual(self._items('vazia.xlsx', _xlsx([])), [])
        self.assertEqual(co_parser.sheet_pages('x.xlsx', b''), [])
