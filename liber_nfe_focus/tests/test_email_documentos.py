# -*- coding: utf-8 -*-
"""O que o cliente recebe quando a casa manda a nota por e-mail.

Até aqui saía só o PDF da fatura. Quem recebe precisa dos dois documentos da
nota: o DANFE, que confere contra a mercadoria, e o XML, que é o documento
fiscal e o que a contabilidade dele guarda.

Testado contra o assistente de envio do `account` de verdade — é ele que
decide o que vai anexo, e é nele que a mudança entra.
"""

import base64

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

from .test_account_move_focus import preparar_documento_latam

CHAVE = '35260712345678000195550010000001231000001236'


@tagged('post_install', '-at_install', 'focus_nfe')
class TestEmailDocumentosDaNota(AccountTestInvoicingCommon):

    # Mesmo motivo do test_account_move_focus: sem fixar o plano genérico, a
    # empresa do common nasce brasileira quando a localização está instalada e
    # traz junto exigências que não têm nada a ver com o que se testa aqui.
    chart_template = 'generic_coa'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Send = cls.env['account.move.send']
        cls.cliente = cls.env['res.partner'].create({
            'name': 'Livraria Exemplo',
            'email': 'compras@livrariaexemplo.com.br',
        })
        cls.livro = cls.env['product.product'].create({
            'name': 'Grande Sertão: Veredas',
            'type': 'consu',
            'list_price': 89.90,
        })

    # -- montagem ------------------------------------------------------
    def _nota_autorizada(self, com_documentos=True, chave=CHAVE,
                         numero='000000123'):
        """Uma fatura no estado em que a SEFAZ a deixa: autorizada."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.cliente.id,
            'invoice_date': '2026-07-30',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.livro.id,
                'name': self.livro.name,
                'quantity': 3,
                'price_unit': 89.90,
                'tax_ids': [(5, 0, 0)],
            })],
        })
        preparar_documento_latam(move)
        move.action_post()
        move.write({
            'focus_ref': 'TESTE-%s' % move.id,
            'focus_status': 'autorizado',
            'focus_numero': numero,
            'focus_serie': '1',
            'nfe_key': chave,
        })
        if com_documentos:
            for sufixo, mimetype, conteudo in (
                ('.pdf', 'application/pdf', b'%PDF-1.4 danfe'),
                # `text/plain`, e não `application/xml`, porque é isso que o
                # banco guarda: o `ir.attachment._check_contents` rebaixa todo
                # anexo parecido com XML quando quem grava não é usuário de
                # sistema, e a emissão roda no usuário que clicou. Escrever
                # `application/xml` aqui faria o teste passar num mundo que
                # não existe -- foi o que deixou o XML sair com o nome errado
                # no primeiro e-mail de verdade.
                ('.xml', 'text/plain', b'<nfeProc/>'),
            ):
                self.env['ir.attachment'].create({
                    'name': '%s%s' % (move.focus_ref, sufixo),
                    'datas': base64.b64encode(conteudo),
                    'mimetype': mimetype,
                    'res_model': 'account.move',
                    'res_id': move.id,
                })
        return move

    def _widget(self, move):
        return self.Send._get_default_mail_attachments_widget(
            move, move._get_mail_template())

    def _anexos_do_email(self, move, widget=None):
        dados = self.Send._get_default_sending_settings(move)
        if widget is not None:
            dados['mail_attachments_widget'] = widget
        return self.Send._get_mail_params(move, dados)['attachments']

    # -- caminho feliz -------------------------------------------------
    def test_danfe_e_xml_vao_anexos_no_email(self):
        move = self._nota_autorizada()

        nomes = [nome for nome, _conteudo in self._anexos_do_email(move)]

        self.assertIn('DANFE-000000123.pdf', nomes)
        self.assertIn('%s-nfe.xml' % CHAVE, nomes)

    def test_o_assistente_lista_os_dois_ja_marcados(self):
        """Quem manda vê o que vai junto, com o nome que o cliente vai ver."""
        move = self._nota_autorizada()

        widget = self._widget(move)

        nossos = [dado for dado in widget
                  if dado['id'] in move._liber_documentos_da_nfe().ids]
        self.assertEqual(len(nossos), 2)
        self.assertEqual(
            sorted(dado['name'] for dado in nossos),
            sorted(['DANFE-000000123.pdf', '%s-nfe.xml' % CHAVE]))
        # Desmarcável (é o `skip` do widget), mas não apagável: o documento
        # fiscal não sai da fatura pelo assistente de envio.
        self.assertTrue(all(dado['protect_from_deletion'] for dado in nossos))
        self.assertTrue(all(not dado['placeholder'] for dado in nossos))

    def test_danfe_vem_antes_do_xml(self):
        """O PDF é o que se abre; o XML é o que se arquiva."""
        move = self._nota_autorizada()

        documentos = move._liber_documentos_da_nfe()

        self.assertEqual(
            [anexo.name.rsplit('.', 1)[-1] for anexo in documentos],
            ['pdf', 'xml'])

    def test_o_xml_rebaixado_a_texto_ainda_e_o_xml_da_nota(self):
        """Quem decide o nome é o sufixo, não o mimetype.

        O Odoo grava o XML como `text/plain` quando quem emite não é usuário
        de sistema. Foi assim que o primeiro e-mail de verdade saiu com a
        referência interna da emissão no lugar da chave de acesso.
        """
        move = self._nota_autorizada()
        xml = move._liber_documentos_da_nfe().filtered(
            lambda anexo: anexo.name.endswith('.xml'))

        self.assertEqual(xml.mimetype, 'text/plain')
        self.assertEqual(move._liber_nome_do_documento(xml),
                         '%s-nfe.xml' % CHAVE)

    # -- casos de borda ------------------------------------------------
    def test_nota_nao_autorizada_nao_manda_documento(self):
        """Enquanto a SEFAZ não autoriza, não há DANFE nem XML que valham."""
        move = self._nota_autorizada()
        move.focus_status = 'processando_autorizacao'

        self.assertFalse(move._liber_documentos_da_nfe())
        self.assertFalse([
            nome for nome, _conteudo in self._anexos_do_email(move)
            if nome.startswith('DANFE-')])

    def test_documento_que_nao_baixou_nao_quebra_o_envio(self):
        """A nota está autorizada mas o download falhou: o e-mail sai assim
        mesmo, com o PDF da fatura, e o resto vem na próxima consulta."""
        move = self._nota_autorizada(com_documentos=False)

        self.assertFalse(move._liber_documentos_da_nfe())
        self.assertTrue(self._widget(move))  # o placeholder da fatura segue lá

    def test_sem_numero_e_sem_chave_o_nome_guardado_serve(self):
        """Nome feio é melhor do que anexo que não vai."""
        move = self._nota_autorizada(chave=False, numero=False)

        nomes = [nome for nome, _conteudo in self._anexos_do_email(move)]

        self.assertIn('%s.pdf' % move.focus_ref, nomes)
        self.assertIn('%s.xml' % move.focus_ref, nomes)

    def test_desmarcar_no_assistente_tira_do_email(self):
        """Quem manda tem a última palavra sobre o que vai anexo."""
        move = self._nota_autorizada()
        widget = self._widget(move)
        for dado in widget:
            if dado['name'] == '%s-nfe.xml' % CHAVE:
                dado['skip'] = True

        nomes = [nome for nome, _conteudo
                 in self._anexos_do_email(move, widget=widget)]

        self.assertNotIn('%s-nfe.xml' % CHAVE, nomes)
        self.assertIn('DANFE-000000123.pdf', nomes)

    def test_o_mesmo_anexo_nao_vai_duas_vezes(self):
        """O widget e os extras do `account` se cruzam: um id, um anexo."""
        move = self._nota_autorizada()

        nomes = [nome for nome, _conteudo in self._anexos_do_email(move)]

        self.assertEqual(nomes.count('DANFE-000000123.pdf'), 1)
        self.assertEqual(nomes.count('%s-nfe.xml' % CHAVE), 1)
