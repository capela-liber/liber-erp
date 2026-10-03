# -*- coding: utf-8 -*-
"""O disparo mensal do mapa: uma CO, o mapa dela, uma vez por mês.

O mapa é ATO DO COMERCIAL, não extrato de cortesia: a casa procura o cliente.
Por isso o disparo não manda um papel solto -- ele abre a operação do mês (a
mesma que o "Gerar operações" abre) e manda o mapa DELA, para que a resposta do
cliente caia numa CO que tem dono, prazo e fila.

O que estes testes seguram:

  - A OPERAÇÃO: abre uma CO por contrato válido com prateleira, reaproveita a
    que já está sendo trabalhada, e não se deixa enganar por rascunho parado em
    coluna recolhida. É a mesma régua do Gerar operações, e é aqui que se prova
    que é a mesma.
  - QUEM: contrato ATIVO e dentro da vigência. Rascunho, suspenso, encerrado e
    vencido ficam de fora; prateleira vazia também, porque sem prateleira não
    há operação a abrir. Cliente SEM E-MAIL ganha a CO assim mesmo e vira
    tarefa para o comercial da conta -- o que falta nele é cadastro.
  - QUANDO: o dia do mês escolhido nas Configurações; em mês curto demais para
    o dia escolhido (31 em fevereiro), o último dia.
  - UMA VEZ SÓ: o cron roda todo dia. Sem o carimbo `map_last_sent_date`, o dia
    certo mandaria a leva de novo -- e abriria a segunda CO do mês.
"""
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'soc_map_schedule')
class TestMapSchedule(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.product = cls.env['product.product'].create({
            'name': 'Grande Sertão: Veredas', 'type': 'consu',
            'is_storable': True, 'list_price': 100.0})
        # O contrato de teste nasce com `user_id` = OdooBot (o env dos testes
        # roda como superusuário), e o robô não conta como responsável. Quem
        # responde por estas fixtures é a vendedora da ficha do cliente, que é
        # também o caso real: no dev, 214 dos 264 clientes têm vendedor e
        # nenhum contrato tem pessoa no campo do comercial.
        cls.vendedora = cls.env['res.users'].create({
            'name': 'Vendedora Padrão', 'login': 'vendedora.padrao@teste.com'})
        cls.env['ir.config_parameter'].sudo().set_param(
            'soc_settlement.map_schedule_enabled', 'True')
        cls.env['ir.config_parameter'].sudo().set_param(
            'soc_settlement.map_schedule_day', '5')

    # -- fixtures -----------------------------------------------------------
    def _agreement(self, nome, email='livraria@teste.com.br', com_estoque=10,
                   **vals):
        """O cliente nasce COM contato de Acertos: é para ele que o mapa vai.

        O e-mail do parâmetro é o do contato de Acertos, e não o da livraria --
        `email=False` é o caso "não há para quem mandar", que abre a tarefa.
        """
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

    def _hoje_e_o_dia(self):
        """Configura o dia do mês como o de hoje, para o cron agir de verdade."""
        hoje = fields.Date.context_today(self.env.user)
        self.env['ir.config_parameter'].sudo().set_param(
            'soc_settlement.map_schedule_day', str(hoje.day))
        return hoje

    def _dia_da_janela(self, dia=5):
        """Uma data real dentro da janela do mês, sem depender de que dia é
        hoje na máquina que roda o teste."""
        hoje = fields.Date.context_today(self.env.user)
        return date(hoje.year, hoje.month, dia)

    def _elegiveis_em(self, hoje):
        """A lista que o cron mandaria SE hoje fosse `hoje`.

        `fields.Date.context_today` lê o fuso do contexto, não a data: não há
        como fingir o dia por lá. Então aqui se chamam as mesmas peças que o
        cron chama, passando a data. O cron de verdade, com a data de verdade,
        é exercitado em `test_o_cron_de_verdade_abre_a_co_e_manda`.
        """
        Agreement = self.env['consignment.agreement']
        ligado, dia = Agreement._map_schedule_config()
        if not ligado or not Agreement._map_schedule_window_open(hoje, dia):
            return Agreement
        return Agreement._shelf_map_due_agreements(hoje)

    def _cos(self, agr):
        return self.env['consignment.settlement'].search(
            [('partner_id', '=', agr.partner_id.id)])

    def _tarefas(self, agr):
        return self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'consignment.agreement'),
            ('res_id', '=', agr.id)])

    def _mails(self, co):
        """O e-mail DO MAPA, que agora pendura na CO.

        Filtrado pelo assunto de propósito: a CO nasce com dono, e atribuir
        dono num mail.thread gera a notificação "foi atribuído a você" -- outro
        mail.mail na mesma CO. Sem este filtro a notificação passaria por mapa
        enviado, exatamente o contrário do que o teste quer provar.
        """
        return self.env['mail.mail'].sudo().search([
            ('model', '=', 'consignment.settlement'), ('res_id', '=', co.id),
            ('subject', 'like', 'Mapa de Consignação')])

    # -- a operação ---------------------------------------------------------
    def test_o_disparo_abre_a_operacao_do_mes(self):
        """O caso que motivou o desenho: ninguém abriu CO para este cliente, e
        o disparo abre -- com a prateleira já lida dentro dela."""
        agr = self._agreement('Livraria da Esquina', com_estoque=7)
        self.assertFalse(self._cos(agr), 'a fixture nasceu com CO')

        co = agr._send_monthly_map()

        self.assertTrue(co, 'o disparo não abriu a operação')
        self.assertEqual(co.state, 'draft')
        self.assertEqual(co.agreement_id, agr)
        linha = co.line_ids
        self.assertEqual(len(linha), 1, 'a CO saiu sem a prateleira lida')
        self.assertEqual(linha.product_id, self.product)
        self.assertEqual(linha.qty_on_shelf, 7)
        # o preço é o do contrato, pelo caminho único
        self.assertAlmostEqual(linha.price_unit, 100.0, places=2)
        self.assertAlmostEqual(linha.discount, 40.0, places=2)

    def test_a_co_do_disparo_tem_dono_de_verdade(self):
        """A resposta do cliente tem de cair numa CO que alguém acompanha.

        O compute da CO cai em `self.env.user` quando o canal não tem líder, e
        no cron esse usuário é o robô: sem isto a operação nasceria de OdooBot e
        a resposta morreria ali -- o buraco que este desenho veio fechar."""
        self._hoje_e_o_dia()
        agr = self._agreement('Livraria com Dono')
        agr.user_id = self.env.ref('base.user_root')

        self.env['consignment.agreement']._cron_send_monthly_maps()

        co = self._cos(agr)
        self.assertEqual(co.user_id, self.vendedora,
                         'a CO do disparo nasceu sem dono de verdade')

    def test_o_mapa_sai_da_co_com_o_pdf(self):
        agr = self._agreement('Livraria do Centro')
        co = agr._send_monthly_map()
        mails = self._mails(co)
        self.assertEqual(len(mails), 1, 'o mapa não foi enfileirado')
        self.assertIn(agr._settlement_contacts(), mails.recipient_ids)
        self.assertTrue(mails.attachment_ids, 'o e-mail saiu sem o PDF do mapa')
        self.assertEqual(agr.map_last_sent_date,
                         fields.Date.context_today(self.env.user))

    def test_reaproveita_a_co_que_ja_esta_sendo_trabalhada(self):
        """Não abre a segunda CO do mês: quem já está em atendimento recebe o
        mapa da operação que o comercial está tocando."""
        agr = self._agreement('Livraria em Atendimento')
        aberta = self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id})

        co = agr._send_monthly_map()

        self.assertEqual(co, aberta, 'abriu uma CO nova por cima da aberta')
        self.assertEqual(len(self._cos(agr)), 1)

    def test_rascunho_parado_em_coluna_recolhida_nao_bloqueia(self):
        """A MESMA régua do Gerar operações: rascunho numa coluna recolhida
        ('Feito') foi abandonado, e não pode prender o cliente para sempre."""
        recolhida = self.env['consignment.settlement.stage'].search(
            [('fold', '=', True)], limit=1)
        if not recolhida:
            self.skipTest('base sem etapa recolhida')
        agr = self._agreement('Livraria Abandonada')
        velha = self.env['consignment.settlement'].create({
            'partner_id': agr.partner_id.id, 'company_id': self.company.id,
            'stage_id': recolhida.id})

        co = agr._send_monthly_map()

        self.assertNotEqual(co, velha, 'o rascunho abandonado prendeu o cliente')
        self.assertEqual(len(self._cos(agr)), 2)

    def test_o_mapa_vai_para_o_contato_de_acertos(self):
        """O endereço do mapa é o do acerto, e NÃO a caixa geral da livraria."""
        agr = self._agreement('Livraria com Acertos')
        acertos = agr._settlement_contacts()
        self.assertEqual(len(acertos), 1, 'a fixture não criou o contato')

        co = agr._send_monthly_map()

        destinatarios = self._mails(co).recipient_ids
        self.assertIn(acertos, destinatarios)
        self.assertNotIn(agr.partner_id, destinatarios,
                         'o mapa foi para a caixa geral da livraria')

    def test_contatos_de_relatorio_entram_no_envio(self):
        agr = self._agreement('Livraria com Relatorio')
        extra = self.env['res.partner'].create({
            'name': 'Compras', 'email': 'compras@teste.com.br'})
        agr.report_contact_ids = [(4, extra.id)]
        co = agr._send_monthly_map()
        destinatarios = self._mails(co).recipient_ids
        self.assertIn(agr._settlement_contacts(), destinatarios)
        self.assertIn(extra, destinatarios)

    # -- o aviso de mensagem automática -------------------------------------
    def test_o_disparo_avisa_que_e_automatico(self):
        agr = self._agreement('Livraria Avisada')
        co = agr._send_monthly_map(automatico=True)
        self.assertIn('mensagem automática', self._mails(co).body_html)

    def test_o_toast_diz_qual_operacao_e_recarrega_a_tela(self):
        """Quem clica num contrato que já tinha CO aberta não vê nada mudar: o
        mapa foi para uma operação que existia. Sem o número dela no aviso, o
        clique parece não ter feito nada -- e sem o `next`, o toast substitui o
        reload e o contador de Consignações fica no número velho."""
        agr = self._agreement('Livraria Avisada de Verdade')
        acao = agr.action_send_consignment_map()
        params = acao['params']
        co = self._cos(agr)
        self.assertIn(co.name, params['message'],
                      'o aviso não diz para qual operação o mapa foi')
        self.assertIn(agr.partner_id.name, params['message'])
        self.assertEqual(params['type'], 'success')
        self.assertEqual(params['next']['tag'], 'soft_reload',
                         'o toast comeu o reload do formulário')

    def test_o_texto_fala_do_que_esta_no_anexo(self):
        """O disparo mensal abre a CO agora: não há devolução, acerto nem
        reposição. Prometer o resumo dos três num papel que só tem a prateleira
        é dizer o que não se cumpre (visto no dev em 24/08/2026)."""
        agr = self._agreement('Livraria Recém-Aberta')
        co = agr._send_monthly_map()
        corpo = self._mails(co).body_html
        self.assertIn('posição atual da mercadoria', corpo)
        self.assertNotIn('resumo desta operação', corpo)

    def test_com_operacao_o_texto_volta_a_ser_o_do_acerto(self):
        """E quando a CO tem o que declarar, o texto é o de sempre: o anexo
        resume a operação, e é disso que ele fala.

        A venda é pendurada na CO à mão, sem rodar o acerto: o que está sob
        teste é o TEXTO, e passar pelo Run traria junto o armazém, o wizard de
        estoque e mais três coisas que não têm nada com o assunto.
        """
        agr = self._agreement('Livraria com Acerto')
        co = agr._settlement_for_map()
        co.sale_order_id = self.env['sale.order'].create(
            {'partner_id': agr.partner_id.id})

        agr._map_template().send_mail(co.id, force_send=False)

        corpo = self._mails(co).sorted('id')[-1].body_html
        self.assertIn('resumo desta operação', corpo)
        self.assertNotIn('posição atual da mercadoria', corpo)

    def test_o_clique_humano_nao_avisa(self):
        """Quem clicou foi gente: dizer 'mensagem automática' seria mentira."""
        agr = self._agreement('Livraria Clicada')
        agr.action_send_consignment_map()
        co = self._cos(agr)
        self.assertNotIn('mensagem automática', self._mails(co).body_html)

    # -- quem fica de fora --------------------------------------------------
    def test_so_contrato_valido(self):
        """Rascunho, suspenso, encerrado e vencido não recebem."""
        hoje = self._dia_da_janela()
        ativo = self._agreement('Ativa')
        suspenso = self._agreement('Suspensa')
        suspenso.action_suspend()
        vencido = self._agreement('Vencida')
        vencido.date_end = hoje - timedelta(days=1)
        rascunho_partner = self.env['res.partner'].create({
            'name': 'Rascunho', 'is_company': True, 'email': 'r@teste.com'})
        rascunho = self.env['consignment.agreement'].create({
            'partner_id': rascunho_partner.id, 'company_id': self.company.id})

        elegiveis = self._elegiveis_em(hoje)
        self.assertIn(ativo, elegiveis)
        self.assertNotIn(suspenso, elegiveis)
        self.assertNotIn(vencido, elegiveis)
        self.assertNotIn(rascunho, elegiveis)

    def test_prateleira_vazia_nao_abre_operacao(self):
        """Sem prateleira não há o que declarar: nem CO, nem mapa."""
        self._hoje_e_o_dia()
        agr = self._agreement('Livraria Zerada', com_estoque=0)
        self.env['consignment.agreement']._cron_send_monthly_maps()
        self.assertFalse(self._cos(agr))

    # -- o cadastro sem e-mail vira tarefa (e ganha a CO assim mesmo) --------
    def test_sem_acertos_abre_a_co_e_a_tarefa(self):
        """A operação do mês é dele também: o que falta é cadastro, e disso
        trata a tarefa. Pular e seguir esconderia justamente o caso que precisa
        de mão humana."""
        self._hoje_e_o_dia()
        comercial = self.env['res.users'].create({
            'name': 'Vendedora', 'login': 'comercial.mapa@teste.com'})
        agr = self._agreement('Livraria Incompleta', email=False)
        agr.user_id = comercial

        self.env['consignment.agreement']._cron_send_monthly_maps()

        co = self._cos(agr)
        self.assertTrue(co, 'o cliente sem e-mail ficou sem a operação do mês')
        self.assertFalse(self._mails(co), 'mandou e-mail para quem não tem')
        tarefas = self._tarefas(agr)
        self.assertEqual(len(tarefas), 1, 'o cadastro sem e-mail passou batido')
        self.assertEqual(tarefas.user_id, comercial,
                         'a tarefa não foi para o comercial da conta')
        self.assertIn(agr.partner_id.name, tarefas.note)
        self.assertFalse(agr.map_last_sent_date,
                         'carimbou como enviado um mapa que não saiu')

    def test_o_robo_nao_e_responsavel(self):
        """No dev os 264 contratos ativos têm OdooBot no campo do comercial:
        veio da migração, não de uma pessoa. Tarefa para o robô é tarefa que
        ninguém vê -- então ela cai para o vendedor da ficha do cliente."""
        self._hoje_e_o_dia()
        vendedor = self.env['res.users'].create({
            'name': 'Vendedor da Ficha', 'login': 'ficha.mapa@teste.com'})
        agr = self._agreement('Livraria Migrada', email=False)
        agr.user_id = self.env.ref('base.user_root')
        agr.partner_id.user_id = vendedor

        self.env['consignment.agreement']._cron_send_monthly_maps()

        self.assertEqual(self._tarefas(agr).user_id, vendedor)

    def test_sem_ninguem_nao_abre_tarefa_orfa(self):
        """Sem vendedor na ficha e sem Gerente de escalonamento, não há a quem
        entregar: melhor nenhuma tarefa do que uma que ninguém vê."""
        self._hoje_e_o_dia()
        agr = self._agreement('Livraria Órfã', email=False)
        agr.user_id = self.env.ref('base.user_root')
        agr.partner_id.user_id = False
        agr.company_id.return_escalation_manager_id = False

        self.env['consignment.agreement']._cron_send_monthly_maps()

        self.assertFalse(self._tarefas(agr))

    def test_o_gerente_de_escalonamento_e_o_ultimo_recurso(self):
        self._hoje_e_o_dia()
        gerente = self.env['res.users'].create({
            'name': 'Gerente', 'login': 'gerente.mapa@teste.com'})
        agr = self._agreement('Livraria sem Vendedor', email=False)
        agr.user_id = self.env.ref('base.user_root')
        agr.partner_id.user_id = False
        agr.company_id.return_escalation_manager_id = gerente

        self.env['consignment.agreement']._cron_send_monthly_maps()

        self.assertEqual(self._tarefas(agr).user_id, gerente)

    def test_a_tarefa_nao_se_multiplica_por_mes(self):
        """Enquanto ninguém tratar, é uma tarefa só -- não uma pilha delas."""
        self._hoje_e_o_dia()
        agr = self._agreement('Livraria Teimosa', email=False)
        self.env['consignment.agreement']._cron_send_monthly_maps()
        agr.map_last_sent_date = False
        self.env['consignment.agreement']._cron_send_monthly_maps()
        self.assertEqual(len(self._tarefas(agr)), 1)

    def test_a_tarefa_sai_no_idioma_de_quem_le(self):
        """A tarefa é do comercial, que trabalha em português -- e não de quem
        roda o cron, que fala inglês. Sem isto ela chegava em inglês."""
        if not self.env['res.lang']._lang_get('pt_BR'):
            self.skipTest('pt_BR não está ativo nesta base')
        self._hoje_e_o_dia()
        comercial = self.env['res.users'].create({
            'name': 'Vendedor', 'login': 'comercial.ptbr@teste.com',
            'lang': 'pt_BR'})
        agr = self._agreement('Livraria em Português', email=False)
        agr.user_id = comercial

        self.env['consignment.agreement'].with_context(
            lang='en_US')._cron_send_monthly_maps()

        tarefa = self._tarefas(agr)
        self.assertEqual(tarefa.summary,
                         'Mapa de consignação: sem contato de Acertos com e-mail')
        self.assertIn('não foi enviado', tarefa.note)

    # -- o orçamento da rodada ----------------------------------------------
    def test_o_cron_declara_o_tamanho_da_fila(self):
        """O executor decide pelo que o cron REPORTA que falta.

        `remaining` em zero quer dizer "terminei", e o cron dorme até amanhã;
        acima de zero, o executor roda o trabalho de novo em seguida. Sem
        declarar o tamanho da fila, o cron do dev mandou DOIS mapas, deu-se por
        concluído e reagendou para o dia seguinte (25/08/2026) — uma leva de
        264 levaria meses.

        Aqui se finge o contexto de cron e se conta o que foi reportado.
        """
        self._hoje_e_o_dia()
        self._agreement('Livraria do Orçamento')
        Agreement = self.env['consignment.agreement']
        reportado = []
        Cron = self.env['ir.cron']
        original = type(Cron)._commit_progress

        def espiao(self_cron, processed=0, *, remaining=None, deactivate=False):
            reportado.append((processed, remaining))
            return 999.0  # orçamento de sobra: a leva não é interrompida

        type(Cron)._commit_progress = espiao
        try:
            Agreement.with_context(
                ir_cron_progress_id=1)._cron_send_monthly_maps()
        finally:
            type(Cron)._commit_progress = original

        self.assertTrue(reportado, 'o cron não reportou progresso nenhum')
        primeiro = reportado[0]
        self.assertEqual(primeiro[0], 0, 'a primeira chamada não é declaração')
        self.assertGreater(
            primeiro[1] or 0, 0,
            'o cron não declarou o tamanho da fila: o executor vai achar que '
            'acabou e dormir até amanhã')
        self.assertEqual(
            reportado[-1][1], 0,
            'a última chamada tem de reportar fila zerada, senão o executor '
            'roda a leva de novo sem ter o que fazer')

    # -- o aviso da leva ----------------------------------------------------
    def _canal(self):
        return self.env.ref('liber_soc_settlement.channel_consignment_replies')

    def test_a_leva_se_explica_no_canal(self):
        """Quem ficou sem mapa aparece no canal, mesmo sem responsável.

        A tarefa avisa quem cuida da conta e depende de haver alguém: no dev,
        de cinco clientes sem contato de Acertos, QUATRO ficaram sem mapa e sem
        ninguém saber (25/08/2026). O canal não depende de responsável.
        """
        hoje = self._hoje_e_o_dia()
        bom = self._agreement('Livraria Avisada')
        orfa = self._agreement('Livraria Órfã do Canal', email=False)
        orfa.user_id = self.env.ref('base.user_root')
        orfa.partner_id.user_id = False
        orfa.company_id.return_escalation_manager_id = False
        antes = len(self._canal().message_ids)

        self.env['consignment.agreement']._cron_send_monthly_maps()

        mensagens = self._canal().message_ids
        self.assertEqual(len(mensagens), antes + 1,
                         'a leva não se explicou no canal')
        corpo = mensagens[0].body
        self.assertIn('Livraria Órfã do Canal', corpo,
                      'o canal não disse quem ficou sem mapa')
        self.assertNotIn(bom.partner_id.name, corpo,
                         'o canal listou quem recebeu')

    def test_leva_sem_sobras_nao_alarma(self):
        """Todo mundo recebeu: o aviso sai, e sai verde -- sem lista de
        problema, para o canal não virar ruído.

        Os contratos que já moram na bancada não têm contato de Acertos, e
        entrariam na leva como sobra: aqui todos ganham um, porque o que está
        sob teste é a leva SEM sobras.
        """
        hoje = self._hoje_e_o_dia()
        self._agreement('Livraria Completa do Canal')
        for outro in self.env['consignment.agreement']._shelf_map_due_agreements(hoje):
            if not outro._settlement_contacts():
                self.env['res.partner'].create({
                    'name': 'Acertos %s' % outro.id, 'type': 'settlement',
                    'email': 'acertos%s@teste.com.br' % outro.id,
                    'parent_id': outro.partner_id.id})
        antes = len(self._canal().message_ids)

        self.env['consignment.agreement']._cron_send_monthly_maps()

        mensagens = self._canal().message_ids
        self.assertEqual(len(mensagens), antes + 1)
        self.assertNotIn('NO map', mensagens[0].body)

    # -- o calendário -------------------------------------------------------
    def test_a_janela_abre_no_dia_escolhido(self):
        """Antes do dia 5, nada. Do dia 5 em diante, a janela do mês está
        aberta -- é ela que deixa uma leva interrompida terminar no dia
        seguinte em vez de sumir o mês inteiro."""
        Agreement = self.env['consignment.agreement']
        self.assertFalse(Agreement._map_schedule_window_open(date(2026, 9, 4), 5))
        self.assertTrue(Agreement._map_schedule_window_open(date(2026, 9, 5), 5))
        self.assertTrue(Agreement._map_schedule_window_open(date(2026, 9, 6), 5))

    def test_mes_curto_cai_no_ultimo_dia(self):
        """Dia 31 em fevereiro: quem escolheu 31 quis dizer 'fim do mês'. Sem
        isto, fevereiro, abril, junho, setembro e novembro passariam em branco
        e ninguém veria o buraco."""
        Agreement = self.env['consignment.agreement']
        self.assertTrue(Agreement._map_schedule_window_open(date(2026, 2, 28), 31))
        self.assertFalse(Agreement._map_schedule_window_open(date(2026, 2, 27), 31))
        # ano bissexto: o último dia é 29, e é nele que abre
        self.assertTrue(Agreement._map_schedule_window_open(date(2028, 2, 29), 31))
        self.assertFalse(Agreement._map_schedule_window_open(date(2028, 2, 28), 31))

    def test_desligado_nao_manda_nada(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'soc_settlement.map_schedule_enabled', 'False')
        agr = self._agreement('Livraria Muda')
        self.assertEqual(
            self.env['consignment.agreement']._cron_send_monthly_maps(), 0)
        self.assertFalse(self._cos(agr), 'abriu CO com o disparo desligado')

    # -- uma vez por mês ----------------------------------------------------
    def test_nao_manda_duas_vezes_no_mesmo_mes(self):
        """O cron roda todo dia; o carimbo é o que impede a segunda leva."""
        hoje = self._dia_da_janela()
        agr = self._agreement('Livraria Única')
        self.assertIn(agr, self._elegiveis_em(hoje))
        agr.map_last_sent_date = hoje
        self.assertNotIn(agr, self._elegiveis_em(hoje))

    def test_o_mes_seguinte_volta_a_valer(self):
        hoje = self._dia_da_janela()
        agr = self._agreement('Livraria Mensal')
        agr.map_last_sent_date = hoje - timedelta(days=40)
        self.assertIn(agr, self._elegiveis_em(hoje))

    # -- o cron, de ponta a ponta -------------------------------------------
    def test_o_cron_de_verdade_abre_a_co_e_manda(self):
        """Fecha o circuito: configura o dia como o de HOJE e chama o cron.

        Os testes acima medem as peças; este mede a peça montada -- é o que
        pega um `model_id` errado no XML do cron, um template sem xmlid, um
        `send_mail` que estoura no meio.
        """
        hoje = self._hoje_e_o_dia()
        agr = self._agreement('Livraria do Cron')

        enviados = self.env['consignment.agreement']._cron_send_monthly_maps()

        self.assertGreaterEqual(enviados, 1)
        self.assertEqual(agr.map_last_sent_date, hoje)
        co = self._cos(agr)
        self.assertEqual(len(co), 1, 'o cron não abriu a operação do mês')
        self.assertEqual(len(self._mails(co)), 1)

    def test_o_nome_antigo_do_cron_continua_valendo(self):
        """O XML do cron é noupdate: o banco chama `_cron_send_shelf_maps` e vai
        continuar chamando. Renomear o método sem este apelido deixaria o cron
        chamando o que não existe -- em silêncio, uma vez por mês."""
        self._hoje_e_o_dia()
        agr = self._agreement('Livraria do Nome Antigo')
        self.assertGreaterEqual(
            self.env['consignment.agreement']._cron_send_shelf_maps(), 1)
        self.assertTrue(self._cos(agr))

    def test_o_cron_nao_repete_a_leva(self):
        self._hoje_e_o_dia()
        agr = self._agreement('Livraria Repetida')
        self.env['consignment.agreement']._cron_send_monthly_maps()
        self.env['consignment.agreement']._cron_send_monthly_maps()
        co = self._cos(agr)
        self.assertEqual(len(co), 1, 'o cron abriu a segunda CO do mês')
        self.assertEqual(len(self._mails(co)), 1,
                         'o cron mandou o mapa duas vezes no mesmo mês')

    # -- o papel ------------------------------------------------------------
    def test_o_cabecalho_tem_espaco_no_papel(self):
        """O bloco da empresa não pode cair em cima do título.

        A régua do wkhtmltopdf, MEDIDA no dev em 24/08/2026 (a primeira versão
        deste teste deduziu o contrário e piorou a colisão):

            topo do cabeçalho = margin_top menos header_spacing
            altura útil dele  = header_spacing

        Com os dois iguais o cabeçalho fica ancorado no alto da folha, que é o
        certo; quem resolve a colisão é o `margin_top`. O bloco da empresa
        (logo, endereço em seis linhas, Tax ID) mede ~51 mm, e o A4 da casa
        começa o corpo aos 52: sobrava 1 mm, e o Tax ID saía por cima do
        título.
        """
        relatorio = self.env.ref(
            'liber_soc_settlement.action_report_consignment_map')
        papel = relatorio.paperformat_id
        self.assertTrue(papel, 'o mapa voltou a depender do A4 da casa')
        self.assertEqual(
            papel.header_spacing, papel.margin_top,
            'header_spacing diferente de margin_top desancora o cabeçalho do '
            'alto da folha e o joga para dentro do corpo')
        self.assertGreaterEqual(
            papel.margin_top, 58,
            'o corpo começa aos %s mm e o bloco da empresa mede ~51: o Tax ID '
            'vai sair por cima do título' % papel.margin_top)

    # -- a configuração -----------------------------------------------------
    # -- de quem o mapa vem -------------------------------------------------
    #
    # "Os clientes preferem pessoas a robôs" (22/09/2026). O mapa saía em nome
    # da empresa; passou a sair em nome de quem a casa escolhesse nas
    # Configurações (um campo único, para a casa inteira). Em 23/09/2026 esse
    # campo foi removido: o automático passa a assinar com o **Líder de
    # Equipe do Canal de Vendas** da própria CO (`team_id.user_id`) -- um
    # remetente único não dizia qual time cuida daquele cliente, e times
    # diferentes têm líderes diferentes. O endereço continua NÃO acompanhando
    # a pessoa, e isso é infraestrutura: o provedor reescreve remetente não
    # autorizado, e o endereço pessoal chegaria ao cliente trocado -- apagando
    # justamente a pessoa.

    def _com_remetente(self, nome='Maria Silva',
                       email='maria.silva@teste.com.br'):
        """Um canal de vendas com líder, e esse líder com e-mail PRÓPRIO.

        O e-mail próprio existe na fixture de propósito: é ele que não pode
        aparecer no remetente. Devolve (pessoa, time) -- quem usa ainda
        precisa ligar `agr.team_id` ao time devolvido, porque o remetente
        automático é por CANAL, não mais um campo único da casa.
        """
        pessoa = self.env['res.users'].create({
            'name': nome, 'login': email, 'email': email})
        time = self.env['crm.team'].create({
            'name': 'Canal de %s' % nome, 'user_id': pessoa.id})
        self.company.email = 'casa@teste.com.br'
        return pessoa, time

    def test_o_remetente_e_o_lider_do_time(self):
        """O cliente vê o nome do líder do SEU canal na caixa de entrada."""
        pessoa, time = self._com_remetente()
        agr = self._agreement('Livraria do Remetente')
        agr.team_id = time.id

        co = agr._send_monthly_map()

        remetente = self._mails(co).email_from
        self.assertIn(pessoa.name, remetente,
                      'o mapa continua saindo em nome do robô')
        self.assertIn('casa@teste.com.br', remetente,
                      'o remetente tem de usar o endereço da casa')

    def test_o_autor_do_chatter_e_o_lider_do_time(self):
        """A CARTA e o CHATTER têm de concordar sobre quem mandou.

        `email_from` aqui é sempre o endereço da casa (nunca o pessoal), e o
        Odoo resolve o autor da mensagem tentando casar esse endereço a um
        parceiro -- como nunca casa (é o endereço da CASA, não da pessoa), o
        autor caía sempre no executor do envio (o robô, num cron de
        verdade), mesmo com o corpo assinado certo. Achado ao vivo em
        23/09/2026."""
        pessoa, time = self._com_remetente()
        agr = self._agreement('Livraria do Autor')
        agr.team_id = time.id

        co = agr._send_monthly_map()

        self.assertEqual(self._mails(co).author_id, pessoa.partner_id,
                         'o chatter não mostra o líder do time como autor')

    def test_o_endereco_pessoal_nao_vai_no_remetente(self):
        """A GUARDA da decisão: vai o nome, nunca o endereço pessoal.

        Endereço fora do domínio autorizado é reescrito pelo provedor (medido
        na virada do e-mail, 09/08/2026: o Odoo manda como `odoo@edlab.press` e
        chega como `odoo@hedra.com.br`). Pôr o pessoal aqui faria a pessoa
        sumir no caminho, que é o oposto do que se quer.
        """
        pessoa, time = self._com_remetente()
        agr = self._agreement('Livraria do Remetente')
        agr.team_id = time.id

        co = agr._send_monthly_map()

        self.assertNotIn(pessoa.email, self._mails(co).email_from,
                         'o endereço pessoal foi para o remetente e será '
                         'reescrito pelo provedor')

    def test_sem_time_ou_sem_lider_nada_muda(self):
        """Sem canal (ou canal sem líder), comportamento de sempre: em nome
        da casa -- não é mais uma configuração para esvaziar, é a ausência de
        canal/líder na própria CO."""
        agr = self._agreement('Livraria sem Time')
        agr.team_id = False

        co = agr._send_monthly_map()

        self.assertEqual(self._mails(co).email_from,
                         self.company.email_formatted or self.env.user.email_formatted)

    def test_sem_lider_o_autor_e_a_empresa_nunca_o_executor(self):
        """"Sem líder, nada muda" valia para a CARTA -- mas o chatter
        continuava mostrando o robô que executa o cron por baixo de uma
        carta assinada "Edlab Press". Incômodo relatado ao vivo em
        23/09/2026, depois do primeiro conserto (que só cobria o caso COM
        líder). O autor cai no parceiro da EMPRESA, nunca vazio."""
        agr = self._agreement('Livraria sem Líder Nenhum')
        agr.team_id = False

        co = agr._send_monthly_map()

        self.assertEqual(self._mails(co).author_id, self.company.partner_id,
                         'sem líder, o chatter tem de mostrar a empresa, '
                         'não o robô que executa o cron')

    def test_a_resposta_volta_para_a_operacao(self):
        """Pessoa no remetente, operação no Reply-To.

        A resposta do cliente não pode cair na caixa individual: na CO ela tem
        dono, prazo e fila, e alguém cobre a ausência de quem assinou.
        """
        pessoa, time = self._com_remetente()
        agr = self._agreement('Livraria da Resposta')
        agr.team_id = time.id

        co = agr._send_monthly_map()

        responder_para = self._mails(co).reply_to or ''
        self.assertNotIn(
            pessoa.email, responder_para,
            'a resposta do cliente foi parar na caixa pessoal, fora da CO')

    def test_a_assinatura_traz_o_nome_do_lider(self):
        """Quem assina o corpo é a mesma pessoa do remetente -- carta de gente
        não termina só com o nome da editora."""
        pessoa, time = self._com_remetente()
        agr = self._agreement('Livraria da Assinatura')
        agr.team_id = time.id

        co = agr._send_monthly_map()

        corpo = self._mails(co).body_html or ''
        self.assertIn(pessoa.name, corpo, 'o corpo não foi assinado')
        self.assertIn(self.company.name, corpo,
                      'a empresa sumiu da assinatura')

    def test_dois_canais_assinam_com_lideres_diferentes(self):
        """A razão de existir da mudança: times diferentes, líderes
        diferentes -- não faz sentido um remetente único para a casa."""
        pessoa_a, time_a = self._com_remetente(
            nome='Líder A', email='lider.a@teste.com.br')
        pessoa_b, time_b = self._com_remetente(
            nome='Líder B', email='lider.b@teste.com.br')
        agr_a = self._agreement('Livraria do Canal A')
        agr_a.team_id = time_a.id
        agr_b = self._agreement('Livraria do Canal B')
        agr_b.team_id = time_b.id

        co_a = agr_a._send_monthly_map()
        co_b = agr_b._send_monthly_map()

        self.assertIn(pessoa_a.name, self._mails(co_a).email_from)
        self.assertIn(pessoa_b.name, self._mails(co_b).email_from)

    # -- quem assina o clique manual é quem clicou, não o líder do time ------
    #
    # 22/09/2026: CO/2026/05748 saiu assinada "Gabriel Godoy" (o remetente
    # automático, então um campo único das Configurações) tendo sido OUTRA
    # pessoa a mandar pelo botão do contrato. O automático virou o Líder de
    # Equipe do canal (23/09/2026); o clique humano continua assinando com
    # `self.env.user`, mesmo quando o canal do cliente tem líder configurado.

    def test_o_clique_humano_assina_com_quem_clicou(self):
        """Mesmo com Líder de Equipe configurado no canal do cliente, o
        clique manual assina com quem clicou -- o líder só entra no
        automático."""
        lider, time = self._com_remetente(nome='Maria Silva',
                                          email='maria.silva@teste.com.br')
        quem_clicou = self.env['res.users'].create({
            'name': 'Sérgio Vendas', 'login': 'sergio.clique@teste.com',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('liber_soc_agreements.group_soc_user').id])]})
        agr = self._agreement('Livraria do Clique Humano')
        agr.team_id = time.id

        agr.with_user(quem_clicou).action_send_consignment_map()

        mail = self._mails(self._cos(agr))
        self.assertIn('Sérgio Vendas', mail.email_from,
                      'o clique manual não assinou com quem clicou')
        self.assertNotIn('Maria Silva', mail.email_from,
                         'o clique manual assinou com o líder do time')
        self.assertIn('Sérgio Vendas', mail.body_html,
                      'o corpo do e-mail não assinou com quem clicou')
        self.assertEqual(mail.author_id, quem_clicou.partner_id,
                         'o chatter não mostra quem clicou como autor')

    def test_clique_manual_sem_time_ainda_assina_com_quem_clicou(self):
        """O clique manual não depende de o cliente ter canal/líder: mesmo
        sem time nenhum, quem manda continua sendo quem clicou -- não
        "ninguém"."""
        quem_clicou = self.env['res.users'].create({
            'name': 'Renata Comercial', 'login': 'renata.clique@teste.com',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('liber_soc_agreements.group_soc_user').id])]})
        agr = self._agreement('Livraria sem Time')
        agr.team_id = False

        agr.with_user(quem_clicou).action_send_consignment_map()

        mail = self._mails(self._cos(agr))
        self.assertIn('Renata Comercial', mail.email_from)

    # -- o insolúvel não pode prender a fila --------------------------------
    #
    # Esta seção nasceu de um laço medido no staging em 21/09/2026: com o
    # interruptor ligado e NENHUM dos 268 contratos com contato de Acertos com
    # e-mail, o cron girou das 20:21 às 20:47 UTC sem parar, `remaining` cravado
    # em 263, e mandou zero mapa. O carimbo de envio só cai no sucesso, então o
    # insolúvel voltava à fila em toda rodada e a leva nunca passava dele.

    def _roda_sem_orcamento(self, rodadas=6):
        """Finge o executor no pior caso: orçamento zerado desde a primeira
        chamada.

        Não é caso exótico, é o normal: `cron_end_time` é fixado UMA vez por
        job (`start_time + MIN_TIME_PER_JOB`, 10s) enquanto o executor chama o
        trabalho no mínimo 10 vezes. Gastos os 10s iniciais, toda chamada
        seguinte recebe zero -- processa um item e volta.
        """
        Agreement = self.env['consignment.agreement']
        Cron = self.env['ir.cron']
        original = type(Cron)._commit_progress

        def sem_orcamento(self_cron, processed=0, *, remaining=None,
                          deactivate=False):
            return 0.0

        type(Cron)._commit_progress = sem_orcamento
        try:
            for _rodada in range(rodadas):
                Agreement.with_context(
                    ir_cron_progress_id=1)._cron_send_monthly_maps()
        finally:
            type(Cron)._commit_progress = original

    def test_o_insoluvel_nao_prende_o_cron_em_laco(self):
        """O contrato sem destinatário não pode barrar quem vem atrás.

        É O TESTE DO DEFEITO. Sem o carimbo de tentativa, a rodada sem
        orçamento processa sempre o PRIMEIRO da fila; se ele é insolúvel, ele
        continua na fila, e a rodada seguinte processa o mesmo -- para sempre.
        A livraria de trás nunca recebe.
        """
        hoje = self._hoje_e_o_dia()
        sem = self._agreement('Livraria Sem Acertos', email=False)
        com = self._agreement('Livraria Com Acertos')

        self._roda_sem_orcamento()

        self.assertEqual(
            com.map_last_sent_date, hoje,
            'a livraria de trás nunca recebeu: o insolúvel prendeu a fila')
        self.assertFalse(
            sem.map_last_sent_date,
            'quem não tem para quem mandar não pode constar como enviado')
        self.assertNotIn(
            sem, self._elegiveis_em(hoje),
            'o insolúvel voltou para a fila e o cron nunca vai reportar zero')
        self.assertNotIn(com, self._elegiveis_em(hoje))

    def test_sem_destinatario_sai_da_fila_do_mes(self):
        """Atendido é atendido, mesmo sem mapa: sai da fila até o mês virar.

        A notícia de que faltou cadastro vai pela tarefa e pelo resumo do
        canal, que é onde se conserta -- não por uma retentativa diária que não
        tem como dar certo sozinha.
        """
        hoje = self._hoje_e_o_dia()
        agr = self._agreement('Livraria Sem Acertos', email=False)

        self.env['consignment.agreement']._cron_send_monthly_maps()

        self.assertEqual(agr.map_last_attempt_date, hoje)
        self.assertFalse(agr.map_last_sent_date)
        self.assertNotIn(agr, self._elegiveis_em(hoje))
        self.assertTrue(
            self._tarefas(agr), 'sem mapa, a tarefa é a única notícia')

    def test_o_mes_seguinte_tenta_de_novo_o_sem_cadastro(self):
        """Sair da fila é DO MÊS, não para sempre: virado o mês, tenta-se de
        novo -- o cadastro pode ter sido consertado."""
        hoje = self._hoje_e_o_dia()
        agr = self._agreement('Livraria Sem Acertos', email=False)
        self.env['consignment.agreement']._cron_send_monthly_maps()
        self.assertNotIn(agr, self._elegiveis_em(hoje))

        agr.sudo().map_last_attempt_date = hoje - timedelta(days=40)
        self.assertIn(agr, self._elegiveis_em(hoje))

    def test_prateleira_vazia_tambem_sai_da_fila(self):
        """Prateleira vazia não abre operação, mas foi ATENDIDA.

        Sem o carimbo ela volta em toda rodada; e se a fila inteira for de
        prateleira vazia, nenhum `_commit_progress` chega a ser chamado dentro
        do laço, o executor fica com a declaração inicial acima de zero e o
        cron roda em falso sem processar nada.
        """
        hoje = self._hoje_e_o_dia()
        agr = self._agreement('Livraria Sem Prateleira', com_estoque=0)

        self.env['consignment.agreement']._cron_send_monthly_maps()

        self.assertEqual(agr.map_last_attempt_date, hoje)
        self.assertFalse(agr.map_last_sent_date)
        self.assertFalse(self._cos(agr), 'prateleira vazia não abre operação')
        self.assertNotIn(agr, self._elegiveis_em(hoje))

    def test_contrato_que_estoura_e_carimbado(self):
        """O CASO DE ERRO: o que estoura também sai da fila.

        O carimbo mora FORA do savepoint e depois do `except` justamente por
        isto: dentro do bloco ele seria desfeito junto com o rollback, o
        contrato voltaria à fila e estouraria de novo -- o mesmo laço, agora
        por exceção em vez de por falta de e-mail.
        """
        hoje = self._hoje_e_o_dia()
        agr = self._agreement('Livraria Que Estoura')
        Agreement = type(self.env['consignment.agreement'])
        original = Agreement._send_monthly_map

        def estoura(self_agr, automatico=True):
            raise ValueError('cadastro torto')

        Agreement._send_monthly_map = estoura
        try:
            self.env['consignment.agreement']._cron_send_monthly_maps()
        finally:
            Agreement._send_monthly_map = original

        self.assertEqual(
            agr.map_last_attempt_date, hoje,
            'o contrato que estourou ficou na fila e vai estourar de novo')
        self.assertFalse(agr.map_last_sent_date)
        self.assertNotIn(agr, self._elegiveis_em(hoje))

    def test_o_carimbo_de_tentativa_nao_mente_sobre_o_envio(self):
        """Quem recebeu tem os dois carimbos; quem não recebeu, só o da
        tentativa. A tela do comercial lê o do envio, e ele não pode mentir."""
        hoje = self._hoje_e_o_dia()
        recebeu = self._agreement('Livraria Que Recebe')
        nao_recebeu = self._agreement('Livraria Sem Acertos', email=False)

        self.env['consignment.agreement']._cron_send_monthly_maps()

        self.assertEqual(recebeu.map_last_sent_date, hoje)
        self.assertEqual(recebeu.map_last_attempt_date, hoje)
        self.assertFalse(nao_recebeu.map_last_sent_date)
        self.assertEqual(nao_recebeu.map_last_attempt_date, hoje)

    def test_dia_invalido_e_recusado(self):
        Settings = self.env['res.config.settings']
        with self.assertRaises(ValidationError):
            Settings.create({
                'map_schedule_enabled': True, 'map_schedule_day': 32})
