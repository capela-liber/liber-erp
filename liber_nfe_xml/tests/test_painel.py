# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

from ..analysis import pipeline

OWN = '03004307'          # Editora Hedra root used by the fixtures
CLIENT = '60316817'


def _nfe(chave, emit_root, dest_doc, cfop, natop, qty, vprod, vdesc=0.0, day='2026-05-10'):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
 <NFe><infNFe Id="NFe{chave}" versao="4.00">
  <ide><nNF>{chave[-6:]}</nNF><serie>1</serie><dhEmi>{day}T10:00:00-03:00</dhEmi>
       <tpNF>1</tpNF><natOp>{natop}</natOp></ide>
  <emit><CNPJ>{emit_root}000159</CNPJ><xNome>Emitente</xNome></emit>
  <dest><CNPJ>{dest_doc}000188</CNPJ><xNome>Livraria Cliente</xNome>
        <enderDest><UF>SP</UF><xMun>Sao Paulo</xMun></enderDest></dest>
  <det nItem="1"><prod><cProd>LIV1</cProd><xProd>Livro Um</xProd><NCM>49019900</NCM>
    <CFOP>{cfop}</CFOP><qCom>{qty}</qCom><vUnCom>{vprod / qty}</vUnCom>
    <vProd>{vprod}</vProd><vDesc>{vdesc}</vDesc></prod></det>
  <total><ICMSTot><vProd>{vprod}</vProd><vNF>{vprod - vdesc}</vNF><vICMS>0</vICMS></ICMSTot></total>
 </infNFe></NFe>
</nfeProc>'''


K = '35260500000000000000550010000000010000000000'


@tagged('post_install', '-at_install')
class TestPainelPipeline(TransactionCase):

    def _build(self, items):
        return pipeline.build(items, {OWN}, {OWN: 'Editora Hedra'})

    def test_receita_e_categorias(self):
        venda = _nfe(K[:-1] + '1', OWN, CLIENT, '5102', 'VENDA DE MERCADORIA', 10, 100.0, 20.0)
        remessa = _nfe(K[:-1] + '2', OWN, CLIENT, '5917', 'REMESSA EM CONSIGNACAO', 5, 50.0)
        recebida = _nfe(K[:-1] + '3', '99999999', OWN, '5102', 'VENDA', 3, 30.0)
        payload = self._build([(venda.encode(), 1), (remessa.encode(), 2), (recebida.encode(), 3)])
        self.assertEqual(payload['meta']['n_notas'], 2)
        self.assertEqual(payload['meta']['recebidas'], 1)
        self.assertEqual(payload['meta']['own'], [OWN])
        self.assertEqual(payload['unids'], ['Editora Hedra'])
        # receita liquida = only the sale, net of discount (100 - 20)
        receita = sum(it[5] for it in payload['itens'] if it[8])
        self.assertEqual(receita, 80.0)
        self.assertIn('REMESSA_CONSIGNACAO', payload['cats'])
        # the consignment remittance shows up as open balance for the client
        pre = payload['precons'][CLIENT + '000188']
        self.assertEqual(pre['rem'], 50.0)
        self.assertEqual(pre['never'], 1)
        # NOTES path carries the panel record id handed in by the caller
        paths = {n[3] for n in payload['notes']}
        self.assertEqual(paths, {'1', '2'})

    def test_consig_hist_e_vazio(self):
        payload = self._build([])
        self.assertIsNone(payload)
        so_venda = _nfe(K[:-1] + '4', OWN, CLIENT, '5102', 'VENDA', 1, 10.0)
        payload = self._build([(so_venda.encode(), 4)])
        self.assertIsNone(payload['consigHist'])

    def test_consig_hist_agrega_por_grupo(self):
        remessa = _nfe(K[:-1] + '5', OWN, CLIENT, '5917', 'REMESSA EM CONSIGNACAO', 5, 50.0, day='2026-04-02')
        acerto = _nfe(K[:-1] + '6', OWN, CLIENT, '5113', 'VENDA CONSIGNADA', 2, 20.0, day='2026-05-03')
        payload = self._build([(remessa.encode(), 5), (acerto.encode(), 6)])
        ch = payload['consigHist']
        self.assertEqual(ch['meta']['n_clientes'], 1)
        client = ch['clients'][0]
        self.assertEqual(client['doc'], CLIENT)
        self.assertEqual(client['R'], 50.0)
        self.assertEqual(client['A'], 20.0)
        self.assertEqual(client['saldo'], 30.0)
        self.assertEqual(ch['months'], ['2026-04', '2026-05'])
