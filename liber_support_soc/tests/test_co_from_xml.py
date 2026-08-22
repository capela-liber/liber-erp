# -*- coding: utf-8 -*-
"""XML de NFe como fonte do assistente da CO (pedido de 22/08/2026).

O que se trava aqui:

* o parser puro (``co_parser.nfe_items``/``nfe_party_docs``) lê itens e
  pontas do XML — e devolve vazio, não exceção, para XML quebrado;
* no assistente o XML VENCE: com ele presente, o texto do e-mail não
  soma linhas por cima;
* a conferência de CNPJ grita quando o parceiro do chamado não é nenhuma
  das duas pontas da NFe — e a criação exige a confirmação explícita.
"""
import base64

from odoo.exceptions import UserError
from odoo.tests import common, tagged

from ..models import co_parser

# CNPJs: o do parceiro certo é o EMITENTE (numa devolução a livraria
# emite); o destinatário é a casa.
CNPJ_LIVRARIA = '11222333000181'
CNPJ_CASA = '99888777000166'

NFE_XML = ('''<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
 <NFe><infNFe Id="NFe35240811222333000181550010000012341000012349">
  <emit><CNPJ>%s</CNPJ><xNome>Livraria do XML</xNome></emit>
  <dest><CNPJ>%s</CNPJ><xNome>EdLab</xNome></dest>
  <det nItem="1"><prod>
    <cProd>INT-1</cProd><cEAN>9788577151234</cEAN>
    <xProd>Fim do SUS?</xProd><qCom>3.0000</qCom>
  </prod></det>
  <det nItem="2"><prod>
    <cProd>9786589705468</cProd><cEAN>SEM GTIN</cEAN>
    <xProd>Banguela</xProd><qCom>2.0000</qCom>
  </prod></det>
 </infNFe></NFe>
</nfeProc>''' % (CNPJ_LIVRARIA, CNPJ_CASA)).encode()


@tagged('post_install', '-at_install')
class TestNfeParserPuro(common.TransactionCase):
    """As funções puras, sem tela no meio."""

    # -- caminho feliz -------------------------------------------------

    def test_nfe_items(self):
        items = co_parser.nfe_items(NFE_XML)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0], {
            'qty': 3, 'label': 'Fim do SUS?', 'isbn': '9788577151234'})
        # SEM GTIN no cEAN não é ISBN — mas o cProd aqui é, e vale
        self.assertEqual(items[1], {
            'qty': 2, 'label': 'Banguela', 'isbn': '9786589705468'})

    def test_nfe_party_docs_traz_as_duas_pontas(self):
        self.assertEqual(co_parser.nfe_party_docs(NFE_XML),
                         {CNPJ_LIVRARIA, CNPJ_CASA})

    def test_is_nfe_xml(self):
        self.assertTrue(co_parser.is_nfe_xml('nota.xml', NFE_XML))
        # planilha não é NFe, mesmo que alguém a renomeie para .xml
        self.assertFalse(co_parser.is_nfe_xml(
            'planilha.xml', b'PK\x03\x04conteudo-de-xlsx'))
        self.assertFalse(co_parser.is_nfe_xml('nota.xml', b''))

    # -- caso de erro --------------------------------------------------

    def test_xml_quebrado_devolve_vazio(self):
        quebrado = NFE_XML[:200]  # truncado no meio de uma tag
        self.assertEqual(co_parser.nfe_items(quebrado), [])
        self.assertEqual(co_parser.nfe_party_docs(quebrado), set())


@tagged('post_install', '-at_install')
class TestCoDesdeXml(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Livraria do XML',
            'is_company': True,
            'vat': CNPJ_LIVRARIA,
            'email': 'xml@livraria.test',
            'allow_consignment': True,
        })
        cls.team = cls.env['liber.support.team'].create({
            'name': 'Comercial XML',
            'company_id': cls.env.company.id,
            'alias_name': 'xml-test',
        })
        cls.livro = cls.env['product.product'].create({
            'name': 'Fim do SUS?', 'type': 'consu', 'is_storable': True,
            'barcode': '9788577151234', 'sale_ok': True,
        })
        cls.Ticket = cls.env['liber.support.ticket']

    def _chamado_com_xml(self, partner=None):
        ticket = self.Ticket.create({
            'name': 'Devolução com nota',
            'team_id': self.team.id,
            'partner_id': (partner or self.partner).id,
        })
        self.env['ir.attachment'].create({
            'name': 'nfe-devolucao.xml',
            'res_model': ticket._name,
            'res_id': ticket.id,
            'datas': base64.b64encode(NFE_XML),
        })
        return ticket

    def _wizard(self, ticket):
        action = ticket.action_open_co_wizard()
        return self.env['liber.support.co.wizard'].browse(action['res_id'])

    # -- caminho feliz -------------------------------------------------

    def test_xml_preenche_as_linhas(self):
        """O botão do chamado pré-seleciona o XML e as linhas nascem
        dele — com o ISBN casando produto por barcode (match Exato)."""
        ticket = self._chamado_com_xml()
        wizard = self._wizard(ticket)
        self.assertEqual(wizard.attachment_id.name, 'nfe-devolucao.xml')
        self.assertEqual(len(wizard.line_ids), 2)
        linha = wizard.line_ids[0]
        self.assertEqual(linha.product_id, self.livro)
        self.assertEqual(linha.qty, 3)
        self.assertEqual(linha.confidence, 'exact')
        # CNPJ da livraria é o emitente: nada a gritar
        self.assertFalse(wizard.cnpj_alert)

    def test_xml_vence_o_email(self):
        """Com XML presente, o texto do e-mail não soma linhas por
        cima — a fonte exata não divide espaço com a leitura fuzzy."""
        ticket = self._chamado_com_xml()
        wizard = self._wizard(ticket)
        wizard.source_text = '5 Um Outro Título Qualquer'
        wizard.action_parse()
        self.assertEqual(len(wizard.line_ids), 2)
        self.assertNotIn('Outro Título',
                         ''.join(wizard.line_ids.mapped('label_source')))

    def test_cnpj_confere_e_cria(self):
        ticket = self._chamado_com_xml()
        wizard = self._wizard(ticket)
        wizard.action_create_co()
        self.assertTrue(ticket.settlement_id)
        self.assertEqual(ticket.settlement_id.line_ids.product_id,
                         self.livro)

    # -- edge: parceiro sem CNPJ na ficha ------------------------------

    def test_parceiro_sem_cnpj_avisa(self):
        sem_doc = self.env['res.partner'].create({
            'name': 'Livraria Sem Ficha',
            'is_company': True,
            'allow_consignment': True,
        })
        wizard = self._wizard(self._chamado_com_xml(partner=sem_doc))
        self.assertTrue(wizard.cnpj_alert)
        self.assertIn('no CNPJ on file', wizard.cnpj_alert)

    # -- caso de erro: CNPJ não bate -----------------------------------

    def test_cnpj_diferente_grita_e_exige_confirmacao(self):
        outra = self.env['res.partner'].create({
            'name': 'Livraria Errada',
            'is_company': True,
            'vat': '11444777000161',
            'allow_consignment': True,
        })
        ticket = self._chamado_com_xml(partner=outra)
        wizard = self._wizard(ticket)
        self.assertTrue(wizard.cnpj_alert)
        self.assertIn('CNPJ mismatch', wizard.cnpj_alert)
        with self.assertRaises(UserError):
            wizard.action_create_co()
        # a confirmação explícita libera — filial emitindo pela matriz
        wizard.cnpj_override = True
        wizard.action_create_co()
        self.assertTrue(ticket.settlement_id)
