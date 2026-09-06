# -*- coding: utf-8 -*-
"""O número da NFe como coluna, nas duas listas em que a nota é procurada.

O número da fatura (INV/2026/00123) e o número da nota (11083) são dois
números diferentes, e quem liga — cliente, transportadora, contador — cita o
segundo, que é o que está impresso no alto do DANFE. Sem a coluna, achar a
fatura de uma nota é abrir uma por uma.

O teste é de view, não de campo: o que quebra aqui é a âncora da herança
sumir do core ou do liber_nfe_remessa, e isso não aparece em teste de ORM.
"""

from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'focus_nfe')
class TestColunaNumeroDaNota(TransactionCase):

    def _colunas(self, xmlid):
        """Os campos que a lista renderiza, já com as heranças aplicadas."""
        view = self.env.ref(xmlid)
        arch = self.env['account.move'].get_view(view_id=view.id, view_type='list')['arch']
        return etree.fromstring(arch).xpath('//field/@name')

    def test_lista_de_faturas_tem_o_numero_da_nota(self):
        self.assertIn('focus_numero', self._colunas('account.view_invoice_tree'),
                      "A lista de faturas ficou sem a coluna do número da NFe.")

    def test_lista_de_remessas_tem_o_numero_da_nota(self):
        self.assertIn('focus_numero',
                      self._colunas('liber_nfe_remessa.view_nfe_remessa_list'),
                      "A lista de remessas ficou sem a coluna do número da NFe.")

    def test_a_coluna_vem_depois_do_numero_da_fatura(self):
        """Os dois números lado a lado: é assim que se compara um com o outro."""
        colunas = self._colunas('account.view_invoice_tree')
        self.assertEqual(colunas[colunas.index('name') + 1], 'focus_numero',
                         "A coluna da NFe saiu de perto do número da fatura.")
