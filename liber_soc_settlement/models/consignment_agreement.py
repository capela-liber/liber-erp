# -*- coding: utf-8 -*-
import calendar
import logging

from markupsafe import Markup

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class ConsignmentAgreement(models.Model):
    _inherit = 'consignment.agreement'

    settlement_ids = fields.One2many(
        'consignment.settlement', 'agreement_id', string='Settlements')
    settlement_count = fields.Integer(
        string='# Settlements', compute='_compute_settlement_count')

    # Carimbo do último mapa AVULSO (o do contrato, sem CO). Serve a uma coisa
    # só: o cron roda todo dia e só um dia do mês é o dia certo -- se o servidor
    # ficou fora do ar naquele dia, ou o cron rodou duas vezes, o carimbo é o
    # que impede a segunda leva. Um por mês, e o mês é o do carimbo.
    map_last_sent_date = fields.Date(
        string='Last Map Sent', readonly=True, copy=False,
        help="When the standalone consignment map (no settlement) was last "
             "e-mailed to this customer. Guards the monthly schedule against "
             "sending twice.")

    def _compute_settlement_count(self):
        groups = self.env['consignment.settlement']._read_group(
            [('agreement_id', 'in', self.ids)], ['agreement_id'], ['__count'])
        counts = {agreement.id: count for agreement, count in groups}
        for agr in self:
            agr.settlement_count = counts.get(agr.id, 0)

    def action_view_settlements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlements'),
            'res_model': 'consignment.settlement',
            'view_mode': 'list,form',
            'domain': [('agreement_id', '=', self.id)],
            'context': {'default_partner_id': self.partner_id.id},
        }

    # ------------------------------------------------------------------
    # Preço do contrato
    # ------------------------------------------------------------------
    def _price_and_discount(self, product, qty=1.0):
        """O preço BRUTO e o desconto em percentual, para este contrato.

        A LISTA MANDA. Um contrato com lista de preços já tem, na lista, o
        percentual que a casa concede a esse cliente -- e `_get_product_price`
        devolve o preço com ele DENTRO. Aplicar por cima o `discount` do
        contrato descontava duas vezes: lista de 30% sobre 100,00 dá 70,00, e
        um contrato de 40% fechava em 42,00 onde o combinado eram 60,00. Os
        dois números são plausíveis, e ninguém percebia.

        Então: com lista, o preço é o de tabela CHEIO e o desconto é o dela; o
        `discount` do contrato é o padrão de quem não tem lista. Regra fixa ou
        fórmula não tem percentual a declarar -- o preço da lista É o preço, e
        o contrato não desconta em cima dele.

        Mora AQUI, e não na linha do acerto, porque quem sabe o preço é o
        contrato -- a lista e o desconto são dele, não da operação. A linha do
        CO pergunta por este caminho; qualquer segunda tela que precise do
        preço combinado com este cliente deve perguntar pelo mesmo, sob pena de
        o mesmo título sair com dois preços em dois papéis.
        """
        self.ensure_one()
        pricelist = self.pricelist_id
        if not pricelist:
            return product.list_price, self.discount
        price, rule_id = pricelist._get_product_price_rule(product, qty)
        rule = self.env['product.pricelist.item'].browse(rule_id)
        if rule.compute_price != 'percentage':
            return price, 0.0
        bruto = rule._compute_price_before_discount(
            product=product, quantity=qty, uom=product.uom_id,
            date=fields.Date.context_today(self), currency=pricelist.currency_id)
        return bruto, rule.percent_price

    # ------------------------------------------------------------------
    # O mapa mensal: uma CO, e o mapa dela
    # ------------------------------------------------------------------
    # O disparo mensal é ATO DO COMERCIAL, não um extrato de cortesia: a casa
    # procura o cliente. Por isso ele não manda um papel solto -- ele abre a
    # operação (a mesma que o "Gerar operações" abre) e manda o mapa DELA. O
    # cliente responde para uma CO que tem dono, prazo e fila; respondendo a um
    # papel sem operação, a resposta não teria onde cair.
    def _settlement_contacts(self):
        """Os contatos de ACERTOS da livraria: quem confere prateleira.

        É um papel na ficha de endereço (`type = settlement`), e não o e-mail
        principal do cliente. Quem responde acerto raramente é quem autoriza
        compra, e mandar o mapa para a caixa geral era contar com a sorte de
        alguém repassar.
        """
        self.ensure_one()
        return self.partner_id._soc_contacts('settlement')

    def _buyer_contacts(self):
        """Os contatos de COMPRADOR: quem autoriza reposição."""
        self.ensure_one()
        return self.partner_id._soc_contacts('buyer')

    def _map_recipients(self):
        """Quem recebe o mapa MENSAL: o contato de Acertos.

        O mapa do disparo é o extrato da prateleira, e prateleira é assunto de
        quem confere: vai para Acertos. Quando a CO já tem conteúdo, quem manda
        é o conteúdo -- ver `consignment.settlement._compute_map_recipient_ids`,
        onde mora a tabela inteira. O cliente em si NÃO entra: mandar para a
        caixa geral é o que este desenho veio substituir.
        """
        self.ensure_one()
        return self._settlement_contacts() | self.report_contact_ids

    def _map_template(self):
        return self.env.ref(
            'liber_soc_settlement.mail_template_consignment_map',
            raise_if_not_found=False)

    def _settlement_for_map(self):
        """A CO que este mapa vai declarar: a que já está aberta, ou uma nova.

        A regra de "já está sendo trabalhada" é a MESMA do Gerar operações
        (`_blocking_draft_domain`), e não uma cópia: rascunho no fluxo bloqueia,
        rascunho parado numa coluna recolhida ("Feito") não. Duas cópias
        divergiriam e o disparo mensal criaria a segunda CO do mês para um
        cliente que já tinha uma.
        """
        self.ensure_one()
        Settlement = self.env['consignment.settlement']
        co = Settlement.search(
            Settlement._blocking_draft_domain(self.partner_id, self.company_id),
            limit=1)
        if not co:
            # O DONO ENTRA NA CRIAÇÃO. O compute da CO cai em `self.env.user`
            # quando o canal não tem líder, e no cron `self.env.user` é o robô:
            # a operação nasceria de OdooBot, e a resposta do cliente cairia
            # numa CO que ninguém acompanha -- que é exatamente o buraco que
            # este desenho veio fechar.
            valores = {
                'partner_id': self.partner_id.id,
                'company_id': self.company_id.id,
            }
            responsavel = self._map_responsible()
            if responsavel:
                valores['user_id'] = responsavel.id
            co = Settlement.create(valores)
        # Relê a prateleira SEMPRE, e não só quando a CO nasce: o mapa promete a
        # posição de hoje. O populate é de mistura (ver a docstring dele) -- a
        # linha já digitada pelo operador sobrevive, some apenas a intocada cujo
        # título saiu da prateleira.
        co.action_populate_from_shelf()
        return co

    def action_send_consignment_map(self):
        """Botão do contrato: manda o mapa agora, pelo mesmo caminho do cron.

        Garante a CO igual ao disparo mensal -- um caminho só, pelo relógio ou
        pela mão. O que muda é só o aviso de mensagem automática, que aqui não
        vai: quem clicou foi gente.
        """
        operacoes = self.env['consignment.settlement']
        for agr in self:
            operacoes |= agr._send_monthly_map(automatico=False)
        # DIZER QUAL OPERAÇÃO, e não só "1 mapa enfileirado". Quem clica num
        # contrato que já tinha CO aberta não vê nada mudar na tela: o mapa foi
        # para uma operação que existia, e sem o número dela o clique parece não
        # ter feito nada (foi o que aconteceu no dev em 24/08/2026).
        if len(self) == 1 and operacoes:
            mensagem = _("Map of %(co)s queued for %(customer)s.",
                         co=operacoes.name,
                         customer=self.partner_id.display_name)
        else:
            mensagem = _('%s map(s) queued for sending.') % len(operacoes)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Consignment Map'),
                'message': mensagem,
                'type': 'success' if operacoes else 'warning',
                'sticky': False,
                # Sem o `next`, a devolução do toast SUBSTITUI o reload padrão
                # do formulário: o botão do contrato abre uma CO e o contador
                # de Consignações continua mostrando o número velho. Mesmo
                # conserto do aviso de volumes (17/08/2026).
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _send_monthly_map(self, automatico=True):
        """Abre (ou reaproveita) a CO e enfileira o mapa dela.

        Devolve a CO quando o mapa foi enfileirado, e vazio quando não foi. A CO
        nasce de todo jeito: cliente sem e-mail continua sendo cliente com
        prateleira, e a operação do mês é dele também -- o que falta é o
        cadastro, e disso trata a tarefa.

        Não envia na hora (`force_send=False`): o PDF é montado e o e-mail vai
        para a fila do Odoo, que é quem sabe despachar 250 mensagens sem
        segurar o cron aqui dentro.
        """
        self.ensure_one()
        template = self._map_template()
        co = self._settlement_for_map()
        # SEM CONTATO DE ACERTOS O MAPA NÃO SAI. A operação do mês abre assim
        # mesmo -- o cliente tem prateleira e o comercial tem trabalho a fazer
        # --, mas o papel não tem para quem ir, e mandar para a caixa geral da
        # livraria é o que este desenho veio substituir.
        if not template or not any(p.email for p in self._map_recipients()):
            return self.env['consignment.settlement']
        template.with_company(self.company_id).with_context(
            mapa_automatico=automatico).send_mail(co.id, force_send=False)
        self.sudo().map_last_sent_date = fields.Date.context_today(self)
        return co

    def _map_responsible(self):
        """Quem responde pela conta, em ordem de especificidade.

        Serve a duas coisas: o dono da CO que o disparo abre e o dono da tarefa
        de cadastro sem e-mail. É a mesma pergunta -- "quem cuida deste cliente"
        -- e por isso tem uma resposta só.

        O comercial do contrato viria primeiro, mas no dev os 264 contratos
        ativos têm `user_id` = OdooBot: o campo foi preenchido pela migração,
        não por uma pessoa. Tarefa atribuída ao robô é tarefa que ninguém vê,
        então o robô (e qualquer usuário arquivado) não conta como responsável
        -- cai para o vendedor da FICHA DO CLIENTE, que 214 dos 264 têm.

        Sobrando ninguém, o Gerente de escalonamento das Configurações da
        consignação, que é o campo onde a casa já diz "quem se incomoda quando
        algo trava". Vazio ele também, não há a quem entregar: o cron registra
        no log e não abre tarefa órfã.
        """
        self.ensure_one()
        robo = self.env.ref('base.user_root', raise_if_not_found=False)

        def gente(user):
            return user and user.active and user != robo and user

        return (gente(self.user_id)
                or gente(self.partner_id.user_id)
                or gente(self.company_id.return_escalation_manager_id)
                or self.env['res.users'])

    def _missing_email_activity_values(self):
        """Resumo e nota da tarefa, no idioma DESTE recordset.

        Os dois textos nascem juntos e no mesmo lugar de propósito: `_()` lê o
        idioma do `self` do frame em que é chamado, então montar o resumo aqui
        e a nota lá fora daria uma tarefa com título em português e corpo em
        inglês. Quem chama passa o `lang` de quem vai LER a tarefa -- o
        comercial da conta --, e não o de quem roda o cron, que fala inglês.
        (Medido no dev em 24/08/2026: antes disso a tarefa chegava em inglês.)

        O resumo é também a CHAVE da idempotência. Que ela dependa do idioma do
        responsável é o preço: trocar a pessoa da conta por outra de idioma
        diferente abre uma tarefa nova ao lado da antiga, uma vez.
        """
        self.ensure_one()
        return {
            'summary': _("Consignment map: no Settlement contact with e-mail"),
            'note': _("The monthly consignment map of %(customer)s was not "
                      "sent: they have no Settlement contact with an e-mail "
                      "address. %(titles)s title(s) are sitting on their shelf "
                      "with no statement going out. Please add a contact of "
                      "type Settlement on the customer, with the e-mail of "
                      "whoever checks the shelf.",
                      customer=self.partner_id.display_name,
                      titles=self.on_shelf_product_count),
        }

    def _schedule_missing_email_activity(self):
        """Cadastro sem e-mail vira TAREFA, não silêncio.

        O mapa que não sai é a única notícia que aquele cliente teria no mês.
        Pular e seguir esconde exatamente o caso que precisa de mão humana: o
        cadastro está incompleto, e quem conserta cadastro de cliente é o
        comercial da conta.

        Idempotente pelo resumo: `mail.activity` só guarda tarefa ABERTA, então
        enquanto ninguém tratar esta, o cron do mês seguinte reconhece a que já
        está lá e não empilha uma segunda. Fechada a tarefa sem o e-mail ser
        preenchido, ela volta no mês seguinte -- e é isso que se quer.
        """
        self.ensure_one()
        responsavel = self._map_responsible()
        if not responsavel:
            _logger.warning(
                "Mapa de consignação: %s (%s) está sem e-mail E sem "
                "responsável -- nem vendedor na ficha do cliente, nem Gerente "
                "de escalonamento nas Configurações. Ninguém foi avisado.",
                self.name, self.partner_id.display_name)
            return False
        contrato = self.with_context(lang=responsavel.lang or self.env.lang)
        valores = contrato._missing_email_activity_values()
        aberta = self.env['mail.activity'].sudo().search_count([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('summary', '=', valores['summary']),
        ])
        if aberta:
            return False
        contrato.sudo().activity_schedule(
            'mail.mail_activity_data_todo',
            summary=valores['summary'],
            note=valores['note'],
            user_id=responsavel.id)
        return True

    # ------------------------------------------------------------------
    # O agendamento
    # ------------------------------------------------------------------
    @api.model
    def _map_schedule_config(self):
        icp = self.env['ir.config_parameter'].sudo()
        ligado = icp.get_param('soc_settlement.map_schedule_enabled', 'False')
        dia = int(icp.get_param('soc_settlement.map_schedule_day', 1) or 1)
        return ligado in ('True', 'true', '1'), min(max(dia, 1), 31)

    @api.model
    def _map_schedule_window_open(self, today, dia_escolhido):
        """Já passou o dia do mês escolhido?

        JANELA, não instante, e por um motivo prático: a leva é de centenas de
        PDFs, e o cron tem um orçamento de tempo. Se ela fosse "só no dia 5" e
        o orçamento acabasse no meio, o resto do mês inteiro ficaria sem mapa e
        ninguém veria o buraco. Aberta a janela, o cron do dia seguinte pega de
        onde parou -- o carimbo por mês garante que quem já recebeu não recebe
        de novo, e no caso normal tudo sai mesmo no dia 5.

        Fevereiro não tem dia 31: quem escolheu 31 quis dizer "o fim do mês",
        então o dia escolhido é aparado no último dia do mês corrente.
        """
        ultimo = calendar.monthrange(today.year, today.month)[1]
        return today.day >= min(dia_escolhido, ultimo)

    @api.model
    def _shelf_map_due_agreements(self, today):
        """Contratos VÁLIDOS hoje que ainda não receberam o mapa neste mês.

        Válido = ativo e dentro da vigência. Não se pergunta por CO aberta aqui
        DE PROPÓSITO: quem tem uma sendo trabalhada recebe o mapa dela mesma
        (ver `_settlement_for_map`), e quem não tem ganha a do mês. Filtrar por
        CO aqui deixaria de fora justamente o cliente já em atendimento.
        """
        primeiro_do_mes = today.replace(day=1)
        return self.sudo().search([
            ('state', '=', 'active'),
            ('location_id', '!=', False),
            '|', ('date_end', '=', False), ('date_end', '>=', today),
            '|', ('map_last_sent_date', '=', False),
                 ('map_last_sent_date', '<', primeiro_do_mes),
        ])

    @api.model
    def _cron_send_shelf_maps(self):
        """O nome que o cron do banco chama. NÃO renomeie.

        O XML do cron é `noupdate="1"` (ver o arquivo, e o porquê): um `-u` não
        reescreve o `code` gravado, então trocar o nome aqui deixaria o cron
        chamando um método que não existe mais -- em silêncio, e a descoberta
        seria no mês seguinte, sem mapa nenhum ter saído.
        """
        return self._cron_send_monthly_maps()

    @api.model
    def _cron_send_monthly_maps(self):
        """O disparo mensal: abre a operação do mês e manda o mapa dela.

        É o "Gerar operações" no relógio. Para cada contrato válido com
        prateleira: reaproveita a CO que já está sendo trabalhada ou abre uma
        nova, relê a prateleira e enfileira o mapa daquela CO para o cliente.

        Idempotente por construção: o cron roda todo dia, só age dentro da
        janela do mês, e o carimbo `map_last_sent_date` tira do lote quem já
        recebeu neste mês -- de modo que rodar duas vezes, ou retomar depois de
        um erro no meio da leva, nunca manda o mesmo mapa duas vezes nem abre a
        segunda CO do mês.
        """
        ligado, dia = self._map_schedule_config()
        if not ligado:
            return 0
        today = fields.Date.context_today(self)
        if not self._map_schedule_window_open(today, dia):
            return 0
        if not self._map_template():
            return 0
        contratos = self._shelf_map_due_agreements(today)
        # O orçamento do cron é do executor: 250 PDFs não cabem numa transação
        # só, e sem os commits parciais uma queda no meio da leva desfaz tudo o
        # que já tinha sido enfileirado -- e a retomada recomeça do zero.
        #
        # Só que `_commit_progress` COMMITA de verdade quando é chamado fora de
        # um cron, e commit é proibido dentro de um teste (e indesejado quando
        # alguém chama isto do `odoo shell` para ensaiar). Então o commit
        # parcial só entra quando há de fato um cron rodando por trás -- é o
        # contexto do executor que diz isso.
        Cron = self.env['ir.cron']
        sob_cron = bool(self.env.context.get('ir_cron_progress_id'))
        # DECLARAR O TAMANHO DA FILA, e não só marcar progresso.
        #
        # O executor decide o que fazer com o cron pelo que ele REPORTA que
        # falta (ver ir_cron._process_jobs): `remaining` em zero significa
        # "terminei", e o cron vai dormir até amanhã; `remaining` acima de zero
        # faz o executor rodar o trabalho DE NOVO, em seguida, até acabar.
        #
        # Sem esta linha o cron reportava zero desde o primeiro item: no dev,
        # com orçamento de 120s, ele mandou DOIS mapas, deu-se por concluído e
        # reagendou para o dia seguinte (25/08/2026). A leva de 264 levaria
        # meses, um punhado por dia, e o log diria "fully done" toda vez.
        if sob_cron:
            orcamento = Cron._commit_progress(remaining=len(contratos))
            _logger.info(
                "Mapa de consignação: %s contrato(s) na fila, %.0fs de "
                "orçamento nesta rodada.", len(contratos), orcamento)
        enviados = sem_email = 0
        interrompido = False
        ficaram_de_fora = self.browse()
        for indice, agr in enumerate(contratos, 1):
            if agr.on_shelf_qty <= 0:
                # Prateleira vazia não tem operação nem mapa. A MESMA regra do
                # Gerar operações, e não uma cópia dela.
                continue
            try:
                # Savepoint, não rollback: um cliente com cadastro torto não
                # pode levar a leva inteira junto, mas um rollback cru também
                # desfaria o que já foi enfileirado antes dele. Desfaz-se só o
                # que ESTE contrato sujou, e a leva segue.
                with self.env.cr.savepoint():
                    if agr._send_monthly_map():
                        enviados += 1
                    else:
                        ficaram_de_fora |= agr
                        if agr._schedule_missing_email_activity():
                            sem_email += 1
            except Exception:
                _logger.exception(
                    "Mapa de consignação: falha em %s (%s)",
                    agr.name, agr.partner_id.display_name)
                continue
            if sob_cron and Cron._commit_progress(
                    1, remaining=len(contratos) - indice) <= 0:
                # Acabou o orçamento DESTA rodada, não a leva. Como sobrou fila,
                # o executor chama o trabalho outra vez em seguida, e ele retoma
                # de onde parou -- o carimbo tira do caminho quem já recebeu.
                interrompido = True
                _logger.info(
                    "Mapa de consignação: orçamento da rodada esgotado com %s "
                    "enviado(s); faltam %s, e o executor volta já.",
                    enviados, len(contratos) - indice)
                break
        # O resumo é da LEVA, não da rodada: só sai quando a fila acabou. Uma
        # leva de 264 é cortada pelo orçamento em várias rodadas seguidas, e um
        # aviso por rodada encheria o canal de pedaço.
        if not interrompido:
            self._post_dispatch_summary(
                self.search_count([('map_last_sent_date', '=', today)]),
                ficaram_de_fora)
        _logger.info(
            "Mapa de consignação: %s mapa(s) enfileirado(s), %s tarefa(s) de "
            "cadastro sem e-mail.", enviados, sem_email)
        return enviados

    @api.model
    def _post_dispatch_summary(self, enviados, ficaram_de_fora):
        """O RESUMO DA LEVA no canal da consignação.

        A tarefa avisa QUEM CUIDA da conta, e é o certo para consertar cadastro.
        Mas ela depende de haver alguém: sem vendedor na ficha e sem Gerente de
        escalonamento, o cron só registrava no log -- e log de cron ninguém lê.
        Medido no dev em 25/08/2026: de cinco clientes sem contato de Acertos,
        QUATRO ficaram sem mapa e sem ninguém saber.

        O canal não depende de responsável nenhum: a leva inteira se explica num
        lugar que a equipe abre. É o aviso de quem toca a operação, não o de
        quem conserta o cadastro -- os dois existem, e por motivos diferentes.
        """
        canal = self.env.ref(
            'liber_soc_settlement.channel_consignment_replies',
            raise_if_not_found=False)
        if not canal or not (enviados or ficaram_de_fora):
            return False
        linhas = [_("%s map(s) sent.") % enviados]
        if ficaram_de_fora:
            nomes = ', '.join(
                a.partner_id.display_name for a in ficaram_de_fora[:20])
            if len(ficaram_de_fora) > 20:
                nomes += _(" and %s more") % (len(ficaram_de_fora) - 20)
            linhas.append(_(
                "%(n)s customer(s) got NO map: no Settlement contact with an "
                "e-mail address. %(names)s",
                n=len(ficaram_de_fora), names=nomes))
        corpo = Markup(
            '<div style="background-color:%(cor)s;border:1px solid #ddd;'
            'border-radius:4px;padding:8px;"><b>%(titulo)s</b><br/>%(texto)s</div>'
        ) % {
            'cor': '#fff3cd' if ficaram_de_fora else '#d1e7dd',
            'titulo': Markup.escape(_("Monthly consignment map")),
            'texto': Markup('<br/>').join(
                Markup.escape(linha) for linha in linhas),
        }
        canal.message_post(body=corpo, message_type='comment',
                           subtype_xmlid='mail.mt_comment')
        return True
