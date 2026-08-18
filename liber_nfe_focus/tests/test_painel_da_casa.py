# -*- coding: utf-8 -*-
"""A nota emitida pela casa, do jeito que ela chega ao painel de XMLs.

O painel junta tudo o que é NFe — o que a casa recebe de fornecedor e o que a
casa emite. Juntar é o desenho; confundir, não. Enquanto a emissão não escrevia
os três campos de procedência, a nota que saía daqui entrava com os padrões de
nota recebida, e no prod as 18 notas da casa ficaram indistinguíveis das 40.827
de terceiros.

Estes testes cobrem o efeito no banco: o que o `_focus_registrar_no_painel`
grava. O download vai falso — nenhum teste sai para a rede.
"""

import base64

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_account_move_focus import preparar_documento_latam

CHAVE = '35260712345678000195550010000001231000001236'
XML = b'<nfeProc><NFe/></nfeProc>'


def baixador(**arquivos):
    """Um `baixar` falso: devolve o que o teste mandou, e None no resto.

    A assinatura é a do fecho que o `_focus_guardar_documentos` passa adiante —
    recebe o nome do campo da resposta da Focus e devolve bytes ou None.
    """
    return lambda campo: arquivos.get(campo)


@tagged('post_install', '-at_install', 'focus_nfe')
class TestPainelDaCasa(AccountTestInvoicingCommon):

    # Mesmo motivo dos vizinhos: sem fixar o plano genérico, a empresa do
    # common nasce brasileira quando a localização está instalada e traz junto
    # exigências que não têm nada a ver com o que se testa aqui.
    chart_template = 'generic_coa'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Painel = cls.env['nfe.xml.panel']
        cls.env.company.write({
            'focus_ambiente': 'homologacao',
            'focus_token_homologacao': 'tok-teste',
        })
        cls.cliente = cls.env['res.partner'].create({'name': 'Livraria'})

    def _nota(self, chave=CHAVE):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.cliente.id,
            'invoice_date': '2026-07-30',
            'invoice_line_ids': [(0, 0, {
                'name': 'Livro', 'quantity': 1, 'price_unit': 10,
                'tax_ids': [(5, 0, 0)]})],
        })
        preparar_documento_latam(move)
        move.action_post()
        move.write({'focus_ref': 'TESTE-1', 'focus_ambiente': 'homologacao',
                    'nfe_key': chave})
        return move

    def _painel_da(self, chave=CHAVE):
        return self.Painel.search([('key', '=', chave)], limit=1)

    # -- o rótulo ------------------------------------------------------
    def test_o_painel_conhece_a_origem_focus(self):
        """Sem o valor na seleção, gravar 'focus' guarda um código que a tela
        não sabe mostrar — e a coluna Origem sai em branco."""
        origens = dict(self.Painel._fields['source'].selection)

        self.assertIn('focus', origens)
        self.assertEqual(origens['focus'], 'Focus NFe')

    # -- caminho feliz -------------------------------------------------
    def test_nota_emitida_entra_marcada_como_da_casa(self):
        nota = self._nota()

        nota._focus_registrar_no_painel(
            {'chave_nfe': 'NFe%s' % CHAVE},
            baixador(caminho_xml_nota_fiscal=XML))

        painel = self._painel_da()
        self.assertTrue(painel, "a emissão tem de criar a linha no painel")
        self.assertEqual(painel.source, 'focus')
        self.assertTrue(painel.system_generated)
        self.assertEqual(painel.xml_type, 'internal')
        # E o que já funcionava continua funcionando.
        self.assertEqual(painel.invoice_id, nota)
        self.assertEqual(painel.company_id, nota.company_id)
        self.assertEqual(base64.b64decode(painel.file), XML)

    def test_linha_que_ja_existia_passa_a_dizer_a_verdade(self):
        """A nota que a casa emitiu volta pela varredura da SEFAZ, e pode ter
        chegado por lá primeiro. Quem emitiu continua sendo a casa."""
        painel = self.Painel.create({
            'key': CHAVE, 'file_name': 'veio-de-fora.xml', 'status': 'imported',
        })
        self.assertEqual(painel.source, 'manual')
        nota = self._nota()

        nota._focus_registrar_no_painel(
            {'chave_nfe': CHAVE}, baixador(caminho_xml_nota_fiscal=XML))

        self.assertEqual(self._painel_da(), painel, "não pode duplicar a chave")
        self.assertEqual(painel.source, 'focus')
        self.assertTrue(painel.system_generated)
        self.assertEqual(painel.xml_type, 'internal')

    def test_nota_de_xml_externo_nao_reemite(self):
        """A nota desta fatura JÁ EXISTE (nasceu de XML autorizado, Olist e
        afins): emitir pela Focus criaria uma segunda NFe para a mesma venda
        na SEFAZ. Porta dupla: o botão some pela view, e esta é a de dentro."""
        self.Painel.create({
            'key': CHAVE, 'file_name': 'olist.xml', 'status': 'imported'})
        nota = self._nota()   # escreve nfe_key=CHAVE -> o elo liga sozinho
        self.assertTrue(nota.nfe_xml_panel_id)

        with self.assertRaises(UserError) as erro:
            nota.action_focus_emitir()

        self.assertIn('segunda nota', str(erro.exception))

    # -- casos de borda ------------------------------------------------
    def test_xml_que_nao_baixou_nao_inventa_linha(self):
        """Documento que não baixou se busca na próxima consulta. Criar a linha
        vazia aqui marcaria como emitida uma nota sem nota dentro."""
        nota = self._nota()

        nota._focus_registrar_no_painel({'chave_nfe': CHAVE}, baixador())

        self.assertFalse(self._painel_da())

    def test_sem_chave_de_acesso_nao_ha_o_que_registrar(self):
        """A chave é a amarração entre XML e fatura; sem ela a linha não teria
        como ser reencontrada, nem por este módulo nem pelo painel."""
        nota = self._nota(chave=False)

        nota._focus_registrar_no_painel(
            {}, baixador(caminho_xml_nota_fiscal=XML))

        self.assertFalse(self.Painel.search([('invoice_id', '=', nota.id)]))
