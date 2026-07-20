# -*- coding: utf-8 -*-
import base64
import gzip
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from ..models import sefaz_dfe_client as dfe

CHAVE1 = '35260600000000000000550010000001231000000001'
CHAVE2 = '35260600000000000000550010000001241000000002'
OWN_CNPJ = '03004307000159'
OTHER_CNPJ = '99888777000166'


def _nfe_proc(chave, emit_cnpj, dest_cnpj):
    return f'''<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
 <NFe><infNFe Id="NFe{chave}" versao="4.00">
  <ide><nNF>{chave[25:34]}</nNF><serie>1</serie><dhEmi>2026-06-01T10:00:00-03:00</dhEmi>
       <tpNF>1</tpNF><natOp>VENDA DE MERCADORIA</natOp></ide>
  <emit><CNPJ>{emit_cnpj}</CNPJ><xNome>Grafica Fornecedora</xNome></emit>
  <dest><CNPJ>{dest_cnpj}</CNPJ><xNome>Editora</xNome>
        <enderDest><UF>SP</UF><xMun>Sao Paulo</xMun></enderDest></dest>
  <det nItem="1"><prod><cProd>P1</cProd><xProd>Servico grafico</xProd><CFOP>5102</CFOP>
    <qCom>1</qCom><vUnCom>10.00</vUnCom><vProd>10.00</vProd></prod></det>
  <total><ICMSTot><vProd>10.00</vProd><vNF>10.00</vNF><vICMS>0</vICMS></ICMSTot></total>
 </infNFe></NFe>
 <protNFe versao="4.00"><infProt><chNFe>{chave}</chNFe><nProt>135260000000001</nProt></infProt></protNFe>
</nfeProc>'''.encode()


def _cancel_event(chave):
    return f'''<procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
 <evento versao="1.00"><infEvento>
   <chNFe>{chave}</chNFe><tpEvento>110111</tpEvento>
   <dhEvento>2026-06-02T10:00:00-03:00</dhEvento>
   <nProt>135260000000002</nProt><xJust>erro de emissao</xJust>
   <descEvento>Cancelamento</descEvento>
 </infEvento></evento>
</procEventoNFe>'''.encode()


def _res_nfe(chave):
    return (f'<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">'
            f'<chNFe>{chave}</chNFe></resNFe>').encode()


@tagged('post_install', '-at_install')
class TestSefazSweep(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.partner_id.vat = '03.004.307/0001-59'
        self.company.write({
            'sefaz_dfe_enabled': True,
            'sefaz_cert_pfx': base64.b64encode(b'fake'),
            'sefaz_cert_password': 'x',
            'sefaz_last_nsu': '0',
        })
        self.Sweep = self.env['nfe.sefaz.sweep']

    def _run_with(self, responses):
        script = list(responses)

        def fake_fetch(model_self, client, cnpj, ult_nsu):
            return script.pop(0)

        cls = type(self.Sweep)
        with patch.object(cls, '_make_client', return_value=object()), \
             patch.object(cls, '_fetch', fake_fetch):
            return self.Sweep.run_sweeps()

    def test_sweep_ingests_dedups_and_cancels(self):
        docs = [
            {'nsu': '7', 'schema': 'procNFe_v4.00', 'xml': _nfe_proc(CHAVE1, OTHER_CNPJ, OWN_CNPJ)},
            {'nsu': '8', 'schema': 'procNFe_v4.00', 'xml': _nfe_proc(CHAVE1, OTHER_CNPJ, OWN_CNPJ)},
            {'nsu': '9', 'schema': 'procEventoNFe_v1.00', 'xml': _cancel_event(CHAVE1)},
            {'nsu': '10', 'schema': 'resNFe_v1.01', 'xml': _res_nfe(CHAVE2)},
        ]
        sweep = self._run_with([
            {'cStat': '138', 'xMotivo': 'Documentos localizados',
             'ultNSU': '10', 'maxNSU': '10', 'docs': docs},
        ])
        self.assertEqual(sweep.status, 'done')
        self.assertEqual((sweep.n_docs, sweep.n_nfe, sweep.n_skipped, sweep.n_events, sweep.n_other),
                         (4, 1, 1, 1, 1))
        self.assertEqual(sweep.nsu_end, '10')
        self.assertEqual(self.company.sefaz_last_nsu, '10')
        panel = self.env['nfe.xml.panel'].search([('key', '=', CHAVE1)])
        self.assertEqual(len(panel), 1)
        self.assertEqual(panel.source, 'sefaz')
        self.assertEqual(sweep.panel_ids, panel)
        event = self.env['nfe.xml.cancel.event'].search([('key', '=', CHAVE1)])
        self.assertEqual(len(event), 1)
        self.assertEqual(event.nfe_id, panel)

    def test_sweep_no_new_documents(self):
        sweep = self._run_with([
            {'cStat': '137', 'xMotivo': 'Nenhum documento localizado',
             'ultNSU': '10', 'maxNSU': '10', 'docs': []},
        ])
        self.assertEqual(sweep.status, 'done')
        self.assertEqual(sweep.n_docs, 0)
        self.assertIn('Nenhum documento', sweep.message)

    def test_sweep_rate_limited(self):
        sweep = self._run_with([
            {'cStat': '656', 'xMotivo': 'Consumo indevido',
             'ultNSU': '5', 'maxNSU': '99', 'docs': []},
        ])
        self.assertEqual(sweep.status, 'rate_limited')
        self.assertEqual(self.company.sefaz_last_nsu, '5')

    def test_sweep_without_certificate(self):
        self.company.sefaz_cert_pfx = False
        sweep = self.Sweep.run_sweeps()
        self.assertEqual(sweep.status, 'error')
        self.assertIn('certificate', sweep.message)

    def test_parse_ret_unpacks_doczip(self):
        xml = _res_nfe(CHAVE2)
        packed = base64.b64encode(gzip.compress(xml)).decode()
        soap = f'''<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body>
 <nfeDistDFeInteresseResponse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
  <nfeDistDFeInteresseResult>
   <retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.35">
    <tpAmb>1</tpAmb><cStat>138</cStat><xMotivo>Documento localizado</xMotivo>
    <ultNSU>000000000000042</ultNSU><maxNSU>000000000000042</maxNSU>
    <loteDistDFeInt><docZip NSU="000000000000042" schema="resNFe_v1.01">{packed}</docZip></loteDistDFeInt>
   </retDistDFeInt>
  </nfeDistDFeInteresseResult>
 </nfeDistDFeInteresseResponse>
</soap:Body></soap:Envelope>'''
        ret = dfe.parse_ret(soap)
        self.assertEqual(ret['cStat'], '138')
        self.assertEqual(len(ret['docs']), 1)
        self.assertEqual(ret['docs'][0]['xml'], xml)
        self.assertEqual(dfe.doc_family(ret['docs'][0]), 'resNFe')
