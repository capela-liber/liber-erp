# -*- coding: utf-8 -*-
"""O CSV do mapa: a MESMA prateleira do PDF, para quem quer automatizar.

Pedido do cliente: quem confere a prateleira à mão lê o PDF; quem tem sistema
próprio quer os números crus, sem digitar. O CSV anda ao LADO do PDF em todo
caminho de envio -- disparo mensal, lote (Ações) e compositor --, nunca no
lugar dele: tirar o PDF quebraria quem já lê ele hoje.
"""
import csv
import io

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMapCsv(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.product = cls.env['product.product'].create({
            'name': 'Grande Sertão: Veredas', 'type': 'consu',
            'is_storable': True, 'list_price': 100.0})
        cls.vendedora = cls.env['res.users'].create({
            'name': 'Vendedora Padrão', 'login': 'vendedora.csv@teste.com'})

    def _agreement(self, nome, email='acertos@teste.com.br', com_estoque=10,
                   **vals):
        partner = self.env['res.partner'].create({
            'name': nome, 'is_company': True,
            'email': 'geral.%s@teste.com.br' % len(nome),
            'user_id': self.vendedora.id})
        if email:
            self.env['res.partner'].create({
                'name': 'Acertos de %s' % nome, 'type': 'settlement',
                'email': email, 'parent_id': partner.id})
        agr = self.env['consignment.agreement'].create(dict({
            'partner_id': partner.id, 'company_id': self.company.id,
            'discount': 40.0,
        }, **vals))
        agr.action_activate()
        if com_estoque:
            self.env['stock.quant']._update_available_quantity(
                self.product, agr.location_id, com_estoque)
        return agr

    def _mails(self, co):
        return self.env['mail.mail'].sudo().search([
            ('model', '=', 'consignment.settlement'), ('res_id', '=', co.id),
            ('subject', 'like', 'Mapa de Consignação')])

    def _linhas_csv(self, dados):
        texto = dados.decode('utf-8-sig')
        return list(csv.reader(io.StringIO(texto), delimiter=';'))

    # -- caminho feliz --------------------------------------------------
    def test_csv_tem_a_mesma_prateleira_do_pdf(self):
        agr = self._agreement('Livraria do CSV', com_estoque=7)
        co = agr._settlement_for_map()

        linhas = self._linhas_csv(co._map_csv())

        self.assertEqual(len(linhas), 2, 'cabeçalho + 1 título esperado')
        cabecalho, linha = linhas
        self.assertEqual(cabecalho[:3], ['ISBN', 'Título', 'Em prateleira'])
        self.assertEqual(linha[1], self.product.name)
        self.assertEqual(linha[2], '7')
        # mesma conta do PDF: qty_on_shelf * price_unit * (1 - desconto/100)
        self.assertAlmostEqual(float(linha[5]), 7 * 100.0 * 0.6, places=2)

    def test_e_mail_do_disparo_mensal_leva_pdf_e_csv(self):
        """O relatório sai .pdf onde há wkhtmltopdf e .html onde não há (como
        no ambiente de teste); o que se mede é que ele CONTINUA indo junto
        com o CSV, não a extensão -- mesma convenção do liber_print_quote."""
        agr = self._agreement('Livraria do Disparo', com_estoque=5)

        co = agr._send_monthly_map()

        mimetypes = self._mails(co).attachment_ids.mapped('mimetype')
        self.assertIn('text/csv', mimetypes,
                      'o CSV não foi anexado no disparo mensal')
        self.assertTrue([m for m in mimetypes if m != 'text/csv'],
                        'o mapa (PDF/HTML) sumiu do disparo mensal: %s' % mimetypes)

    def test_lote_via_acoes_tambem_leva_o_csv(self):
        """"vale também para o mapa enviado via CO" -- o lote do menu Ações
        (sem compositor) é um desses caminhos."""
        agr = self._agreement('Livraria do Lote', com_estoque=3)
        co = agr._settlement_for_map()

        co.action_send_map_batch()

        mimetypes = self._mails(co).attachment_ids.mapped('mimetype')
        self.assertIn('text/csv', mimetypes)
        self.assertTrue([m for m in mimetypes if m != 'text/csv'],
                        'o mapa (PDF/HTML) sumiu do lote: %s' % mimetypes)

    def test_compositor_abre_com_pdf_e_csv(self):
        """O caminho da tela: o compositor abre com os dois, PDF e CSV."""
        agr = self._agreement('Livraria do Compositor', com_estoque=4)
        co = agr._settlement_for_map()

        acao = co.action_send_map()
        compositor = self.env['mail.compose.message'].with_context(
            **acao['context']).create({})

        nomes = compositor.attachment_ids.mapped('name')
        self.assertTrue(any(n.endswith('.csv') for n in nomes),
                        'o CSV não entrou no compositor: %s' % nomes)
        self.assertTrue([n for n in nomes if not n.endswith('.csv')],
                        'o mapa em PDF sumiu do compositor: %s' % nomes)

    def test_a_conversa_do_chatter_nao_leva_csv(self):
        """"Enviar mensagem" no chatter é conversa, não mapa -- mesma guarda
        do liber_print_quote para a ficha técnica."""
        agr = self._agreement('Livraria da Conversa', com_estoque=1)
        co = agr._settlement_for_map()

        compositor = self.env['mail.compose.message'].with_context(
            default_model='consignment.settlement', default_res_ids=co.ids,
            default_composition_mode='comment').create({})

        self.assertFalse(
            compositor.attachment_ids,
            'o chatter abriu com anexo: %s'
            % compositor.attachment_ids.mapped('name'))

    # -- edge case: sem prateleira, sem CSV ------------------------------
    def test_prateleira_vazia_nao_gera_csv(self):
        agr = self._agreement('Livraria Vazia', com_estoque=0)
        co = self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id})
        self.assertFalse(co.line_ids, 'a fixture nasceu com linha')

        self.assertFalse(co._map_csv())
        self.assertFalse(co._map_csv_attachment())

    def test_o_anexo_se_refaz_e_nao_se_acumula(self):
        """Entre um envio e outro a prateleira muda; CSV velho é pior que
        nenhum -- mesmo comportamento do PDF/planilha do liber_print_quote."""
        agr = self._agreement('Livraria do Reenvio', com_estoque=2)
        co = agr._settlement_for_map()
        primeiro = co._map_csv_attachment()

        self.env['stock.quant']._update_available_quantity(
            self.product, agr.location_id, 9)
        # `qty_on_shelf` não é `store`: lê o quant na hora, mas o valor já
        # lido por `primeiro` fica em cache no recordset. Sem invalidar, a
        # releitura enxergaria a prateleira de ANTES do reforço -- o que não
        # acontece de verdade, porque cada disparo roda numa transação nova.
        co.line_ids.invalidate_recordset(['qty_on_shelf'])
        co.action_populate_from_shelf()
        segundo = co._map_csv_attachment()

        self.assertNotEqual(primeiro.id, segundo.id)
        self.assertFalse(primeiro.exists(), 'o CSV velho ficou para trás')
        linhas = self._linhas_csv(segundo.raw)
        self.assertEqual(linhas[1][2], '11', 'o CSV não seguiu a prateleira nova')

    # -- erro/exceção -----------------------------------------------------
    def test_csv_exige_um_registro_por_vez(self):
        """`_map_csv_attachment` chama `ensure_one`: mandar duas CO de uma vez
        é erro de chamada, não "junta tudo num anexo só"."""
        agr1 = self._agreement('Livraria A do Erro', com_estoque=1)
        agr2 = self._agreement('Livraria B do Erro', com_estoque=1)
        cos = agr1._settlement_for_map() | agr2._settlement_for_map()

        with self.assertRaises(ValueError):
            cos._map_csv_attachment()
