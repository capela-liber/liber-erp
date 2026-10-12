# -*- coding: utf-8 -*-
"""A configuração da Focus mora numa aba própria do formulário da empresa.

Até 09/10/2026 o bloco entrava no fim da folha, depois do caderno, e aparecia
embaixo de qualquer aba aberta -- com "Direitos Autorais" aberta, parecia
configuração de direitos autorais. O teste lê o formulário já montado (com
todas as heranças instaladas), que é o que a tela recebe."""
from lxml import etree

from odoo.tests import TransactionCase, tagged

CAMPOS_FOCUS = ('focus_ambiente', 'focus_token_producao',
                'nfe_proximo_numero_producao', 'focus_operacao_padrao_id')


@tagged('post_install', '-at_install', 'focus_nfe')
class TestFormularioEmpresa(TransactionCase):

    def _arch(self):
        view = self.env.ref('base.view_company_form')
        arch = self.env['res.company'].get_views(
            [(view.id, 'form')])['views']['form']['arch']
        return etree.fromstring(arch)

    def test_aba_nfe_dentro_do_caderno(self):
        doc = self._arch()
        pages = doc.xpath("//notebook/page[@name='focus_nfe_page']")
        self.assertEqual(len(pages), 1, "a aba NFe tem de existir, uma vez só")
        self.assertEqual(pages[0].get('string'), 'NFe')
        for campo in CAMPOS_FOCUS:
            self.assertTrue(
                pages[0].xpath(".//field[@name='%s']" % campo),
                "%s tem de estar dentro da aba NFe" % campo)

    def test_nenhum_campo_focus_fora_das_abas(self):
        # O caso que motivou a mudança: o bloco solto depois do caderno.
        doc = self._arch()
        soltos = doc.xpath(
            "//sheet/*[not(self::notebook)]//field[starts-with(@name, 'focus_')]"
            " | //sheet/group[@name='focus_nfe']")
        self.assertFalse(
            soltos, "configuração da Focus fora das abas: %s"
            % [s.get('name') for s in soltos])

    def test_aba_nfe_nao_e_a_primeira(self):
        # Quem abre a empresa cai em "Informações gerais", não na NFe.
        doc = self._arch()
        primeira = doc.xpath("//notebook/page")[0]
        self.assertEqual(primeira.get('name'), 'general_info')
