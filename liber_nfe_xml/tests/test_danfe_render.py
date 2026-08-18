# -*- coding: utf-8 -*-
"""A DANFE nasce do XML — e agora nasce de verdade.

O renderizador antigo (pytrustnfe) nunca esteve instalado em servidor nenhum
da casa: o preview de DANFE era um botão que só produzia "Invalid file!". A
troca pela brazilfiscalreport (18/08/2026) é pintada aqui com um nfeProc real
anonimizado — se a biblioteca sumir do ambiente, o teste PULA e o erro de
tela diz o nome dela e como instalar.
"""
import base64
import os
import unittest

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

try:
    from brazilfiscalreport.danfe import Danfe
except ImportError:
    Danfe = None

FIXTURE = os.path.join(os.path.dirname(__file__), 'nfe_exemplo.xml')
REPORT = 'liber_nfe_xml.main_template_report_nfe_panel'


@tagged('post_install', '-at_install')
class TestDanfeRender(TransactionCase):
    def _painel(self, com_xml=True):
        vals = {
            'key': '35260835288052000190550020000009361132463682',
            'file_name': 'nfe_exemplo.xml',
            'status': 'imported',
        }
        if com_xml:
            with open(FIXTURE, 'rb') as f:
                vals['file'] = base64.b64encode(f.read())
        return self.env['nfe.xml.panel'].create(vals)

    @unittest.skipIf(Danfe is None, "brazilfiscalreport não instalada")
    def test_danfe_renderiza_do_xml(self):
        painel = self._painel()

        pdf, tipo = self.env['ir.actions.report']._render_qweb_pdf(
            REPORT, res_ids=[painel.id])

        self.assertEqual(tipo, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'),
                        "o retorno tem de ser um PDF de verdade")
        self.assertGreater(len(pdf), 1000,
                           "uma DANFE de uma página tem alguns KB")

    def test_br_do_olist_vira_quebra_de_linha(self):
        """O infCpl do Olist traz '<br />' literal; no papel vira linha nova."""
        Report = self.env['ir.actions.report']
        entrada = ('<infCpl>[CODIGO]&lt;br /&gt;infAdFisco - texto.'
                   '&lt;br/&gt;&lt;BR /&gt;Tributos: R$ 1.</infCpl>')

        saida = Report._liber_infcpl_sem_html(entrada)

        self.assertNotIn('&lt;br', saida.lower())
        self.assertEqual(saida.count('&#10;'), 3)
        self.assertIn('[CODIGO]&#10;infAdFisco', saida,
                      "o texto fiscal em si não pode mudar")

    @unittest.skipIf(Danfe is None, "brazilfiscalreport não instalada")
    def test_sem_xml_explica_em_vez_de_quebrar(self):
        painel = self._painel(com_xml=False)

        with self.assertRaises(UserError) as erro:
            self.env['ir.actions.report']._render_qweb_pdf(
                REPORT, res_ids=[painel.id])

        self.assertIn('XML', str(erro.exception))
