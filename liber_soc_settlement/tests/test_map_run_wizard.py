# -*- coding: utf-8 -*-
"""O wizard RUN não manda na hora do clique -- só pede.

Centenas de PDFs a ~1s cada travariam o navegador de quem clicou por
minutos. `action_confirm` carimba `map_run_requested_at` nas COs elegíveis e
devolve a tela na hora, com um aviso de que o envio roda em segundo plano; é
o cron `_cron_process_map_run_queue` quem manda de verdade.
"""
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMapRunWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.product = cls.env['product.product'].create({
            'name': 'Grande Sertão: Veredas', 'type': 'consu',
            'is_storable': True, 'list_price': 100.0})

    def _agreement(self, nome, email='geral@teste.com.br', com_estoque=5,
                   **vals):
        partner = self.env['res.partner'].create({
            'name': nome, 'is_company': True, 'email': email})
        agr = self.env['consignment.agreement'].create(dict({
            'partner_id': partner.id, 'company_id': self.company.id,
            'discount': 30.0,
        }, **vals))
        agr.action_activate()
        if com_estoque:
            self.env['stock.quant']._update_available_quantity(
                self.product, agr.location_id, com_estoque)
        return agr

    def _wizard(self):
        return self.env['consignment.map.run.wizard'].create({})

    def _mails(self, co):
        return self.env['mail.mail'].sudo().search([
            ('model', '=', 'consignment.settlement'), ('res_id', '=', co.id),
            ('subject', 'like', 'Mapa de Consignação')])

    # -- caminho feliz --------------------------------------------------
    def test_confirmar_carimba_e_nao_manda_na_hora(self):
        """O clique só pede o envio -- quem manda é o cron de fundo."""
        agr = self._agreement('Livraria do Wizard')
        co = agr._settlement_for_map()
        wizard = self._wizard()

        acao = wizard.action_confirm()

        co.invalidate_recordset()
        self.assertTrue(co.map_run_requested_at,
                        'o clique não carimbou a fila')
        self.assertFalse(self._mails(co),
                         'o clique mandou na hora -- devia só ter pedido')
        self.assertIn('background', acao['params']['message'],
                      'o aviso não diz que roda em segundo plano')

    def test_o_cron_de_fundo_manda_o_que_foi_pedido(self):
        """A base de teste já tem outras COs em rascunho (seeds de outros
        testes/módulos) que a fila também processa -- por isso o que se mede
        é O QUE ACONTECE COM A CO DESTE TESTE, não um total global."""
        agr = self._agreement('Livraria do Cron de Fundo')
        co = agr._settlement_for_map()
        self._wizard().action_confirm()

        self.env['consignment.settlement']._cron_process_map_run_queue()

        co.invalidate_recordset()
        self.assertFalse(co.map_run_requested_at,
                         'o carimbo não foi limpo depois do envio')
        mail = self._mails(co)
        self.assertEqual(len(mail), 1)
        # O relatório sai .pdf onde há wkhtmltopdf e .html onde não há (como
        # no ambiente de teste); mede-se que ele CONTINUA indo junto com o
        # CSV, não a extensão -- mesma convenção do liber_print_quote.
        mimetypes = mail.attachment_ids.mapped('mimetype')
        self.assertIn('text/csv', mimetypes,
                      'o CSV não foi junto no envio da fila do wizard')
        self.assertTrue([m for m in mimetypes if m != 'text/csv'],
                        'o mapa (PDF/HTML) sumiu da fila do wizard: %s' % mimetypes)

    def test_a_fila_assina_como_automatico_nao_como_odoobot(self):
        """O cron de fundo roda como o executor do sistema (OdooBot na vida
        real) -- e é por isso que a assinatura segue o padrão do disparo
        automático (Líder de Equipe do canal), não `self.env.user`. Achado
        ao vivo em 23/09/2026: um envio real do wizard saiu assinado
        "OdooBot" em vez de uma pessoa."""
        lider = self.env['res.users'].create({
            'name': 'Líder do Canal', 'login': 'lider.canal@teste.com'})
        time = self.env['crm.team'].create({
            'name': 'Canal do Wizard', 'user_id': lider.id})
        agr = self._agreement('Livraria do Cron Como OdooBot')
        agr.team_id = time.id
        co = agr._settlement_for_map()
        self._wizard().action_confirm()

        robo = self.env.ref('base.user_root')
        self.env['consignment.settlement'].with_user(
            robo)._cron_process_map_run_queue()

        mail = self._mails(co)
        self.assertIn(lider.name, mail.email_from,
                      'a fila não assinou com o líder do time')
        self.assertNotIn('OdooBot', mail.email_from,
                         'a fila assinou com o robô que executa o cron')
        self.assertEqual(mail.author_id, lider.partner_id,
                         'o chatter mostra o robô do executor, não o líder '
                         '-- a carta acerta o texto e o chatter continua '
                         'errado')

    def test_a_fila_rele_a_prateleira_antes_de_mandar(self):
        """A CO carimbada pelo clique pode nunca ter sido populada -- o cron
        de fundo tem de reler a prateleira, senão manda com `line_ids`
        vazio: o PDF sai com a tabela em branco (sem erro -- por isso passou
        despercebido) e o CSV nem chega a ser criado. Achado ao vivo em
        23/09/2026."""
        agr = self._agreement('Livraria Nunca Populada', com_estoque=6)
        co = self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id})
        self.assertFalse(co.line_ids, 'a fixture já nasceu populada')
        self._wizard().action_confirm()

        self.env['consignment.settlement']._cron_process_map_run_queue()

        co.invalidate_recordset()
        self.assertTrue(co.line_ids, 'a fila não releu a prateleira')
        mail = self._mails(co)
        self.assertIn('text/csv', mail.attachment_ids.mapped('mimetype'),
                      'sem reler a prateleira, o CSV não tinha linha nenhuma')

    # -- edge case: sem destinatário não trava a fila ------------------------
    def test_sem_destinatario_sai_da_fila_sem_travar(self):
        agr = self._agreement('Livraria Sem E-mail', email=False)
        co = agr._settlement_for_map()
        self._wizard().action_confirm()

        self.env['consignment.settlement']._cron_process_map_run_queue()

        co.invalidate_recordset()
        self.assertFalse(co.map_run_requested_at,
                         'sem destinatário, a CO voltaria para a fila para sempre')
        self.assertFalse(self._mails(co))

    # -- erro: um item torto não prende os outros ----------------------------
    def test_item_que_estoura_nao_prende_os_outros_nem_a_fila(self):
        bom = self._agreement('Livraria Boa da Fila')
        ruim = self._agreement('Livraria Que Estoura na Fila')
        co_bom = bom._settlement_for_map()
        co_ruim = ruim._settlement_for_map()
        self._wizard().action_confirm()

        Klass = type(self.env['consignment.settlement'])
        original = Klass._map_csv_attachment

        def estoura(self):
            if self.id == co_ruim.id:
                raise ValueError('anexo torto')
            return original(self)

        Klass._map_csv_attachment = estoura
        try:
            self.env['consignment.settlement']._cron_process_map_run_queue()
        finally:
            Klass._map_csv_attachment = original

        self.assertTrue(self._mails(co_bom), 'o item bom da fila não foi enviado')
        self.assertFalse(self._mails(co_ruim), 'o item que estourou não podia ter mandado mail')
        co_ruim.invalidate_recordset()
        self.assertFalse(
            co_ruim.map_run_requested_at,
            'o item que estourou ficou preso na fila para sempre')
