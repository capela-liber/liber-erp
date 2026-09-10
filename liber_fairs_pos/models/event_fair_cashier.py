# -*- coding: utf-8 -*-
"""Quem opera cada caixa da feira.

Antes se perguntava QUANTOS caixas. Perguntar quantos é contar máquinas; o
que a feira precisa saber é QUEM está em cada uma -- é o nome que aparece na
tela de quem abre o balcão, é por ele que se acha o caixa no meio dos caixas
da casa, e é ele que responde pela gaveta no fim do dia.

E quem é uma pessoa da casa, não um texto digitado: escolhe-se o CONTATO, e
pronto. Digitar o nome à mão produziria "Fábia", "Fabia Alvim" e "F. Alvim"
como se fossem três pessoas.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EventFairCashier(models.Model):
    _name = 'event.fair.cashier'
    _description = 'Fair Cash Register Operator'
    _order = 'fair_id, sequence, id'

    fair_id = fields.Many2one(
        'event.fair', string='Fair', required=True, ondelete='cascade',
        index=True)
    sequence = fields.Integer(default=10)
    partner_id = fields.Many2one(
        'res.partner', string='Operator', required=True,
        help="Who works this register. The register is named after the fair "
             "and this person.")
    # O rótulo, guardado: é ele que nomeia o caixa e que a restrição usa, e
    # ele não pode mudar de baixo do caixa se alguém corrigir o cadastro do
    # contato no ano que vem.
    name = fields.Char(
        string='Name', compute='_compute_name', store=True, readonly=True)
    # OPERADOR ou GERENTE, decidido aqui e não na tela de usuários: quem monta
    # o evento sabe quem vende no balcão e quem responde pelo evento, e
    # ninguém vai à administração de usuários por causa de uma feira de três
    # dias.
    # ATENDENTE e SUPERVISOR, e não operador e gerente: "gerente" é cargo da
    # casa (o gerente comercial), e usar a mesma palavra para a função de três
    # dias na praça confundia as duas coisas em toda conversa.
    role = fields.Selection(
        [('operator', 'Attendant'), ('manager', 'Supervisor')],
        string='Profile', default='operator', required=True,
        help="The attendant sells at their own register and, alone on site, "
             "confirms the load that arrives. The supervisor does that and "
             "what only somebody on site can do: opens a colleague's "
             "register to sort out a problem, discounts beyond the practised "
             "price, counts the table, closes the day, records losses and "
             "sends the goods home. Planning the event and agreeing what "
             "each person earns belong to whoever puts the fair together, "
             "back at the house.")
    user_id = fields.Many2one(
        'res.users', string='Account', compute='_compute_user',
        store=True, readonly=True,
        help="The login of this contact, if there is one. Without an "
             "account, the person works the counter but does not open the "
             "system.")
    access_granted = fields.Boolean(
        string='Access given', readonly=True, copy=False,
        help="This module gave the access, and this module takes it back "
             "when the event comes home.")
    # O QUE FOI DADO, guardado. Sem isto, tirar o acesso no fim do evento
    # tiraria também o que a pessoa já tinha por conta própria -- o caixa da
    # loja que veio ajudar na feira perderia o PDV do dia a dia.
    granted_group_ids = fields.Many2many(
        'res.groups', string='Groups given', readonly=True, copy=False)
    access_state = fields.Selection(
        [('no_account', 'No account'), ('granted', 'Has access'),
         ('ended', 'Access ended')],
        string='Access', compute='_compute_access_state')
    pos_config_id = fields.Many2one(
        'pos.config', string='Register', readonly=True, copy=False)
    company_id = fields.Many2one(related='fair_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    # ------------------------------------------------------------------
    # o dinheiro de quem trabalha o evento
    # ------------------------------------------------------------------
    commission_pc = fields.Float(
        string='Commission (%)', digits=(5, 2), default=0.0,
        help="Percentage on what THIS person sold at their own register.")
    daily_rate = fields.Monetary(
        string='Daily rate', currency_field='currency_id',
        help="What this person is paid per day of the event.")
    days = fields.Integer(
        string='Days', default=0,
        help="How many days this person worked. Starts as the length of the "
             "event and is corrected here when somebody works fewer days.")
    pos_amount = fields.Monetary(
        string='Sold', currency_field='currency_id',
        compute='_compute_dinheiro', help="What this register sold.")
    commission_amount = fields.Monetary(
        string='Commission', currency_field='currency_id',
        compute='_compute_dinheiro')
    daily_amount = fields.Monetary(
        string='Dailies', currency_field='currency_id',
        compute='_compute_dinheiro')
    loss_share = fields.Monetary(
        string='Loss share', currency_field='currency_id',
        compute='_compute_dinheiro',
        help="This person's share of what the event lost, at cost, split "
             "equally between the team. The table is everybody's.")
    net_amount = fields.Monetary(
        string='To pay', currency_field='currency_id',
        compute='_compute_dinheiro')
    uncovered_loss = fields.Monetary(
        string='Still owed', currency_field='currency_id',
        compute='_compute_dinheiro',
        help="The part of the loss share that commission and dailies did not "
             "cover. Nobody pays a negative bill: it is written here so the "
             "conversation happens with a number on the table.")
    bill_id = fields.Many2one(
        'account.move', string='Bill', readonly=True, copy=False)

    @api.depends('commission_pc', 'daily_rate', 'days', 'pos_config_id',
                 'fair_id.loss_ids.value', 'fair_id.loss_ids.charged_to_team',
                 'fair_id.cashier_ids')
    def _compute_dinheiro(self):
        """Vendido, comissão, diária, rateio da perda e o líquido.

        Duas decisões da casa moram aqui, e as duas foram escolhidas para
        serem explicáveis em voz alta para quem está no balcão:

          - a COMISSÃO é sobre o que a PESSOA vendeu no caixa dela. Quem
            vendeu mais, ganha mais;
          - a PERDA rateia IGUAL entre a equipe. A mesa é guarda coletiva: não
            se sabe de quem era o exemplar que sumiu, e cobrar de quem vendeu
            mais seria punir quem trabalhou mais.

        O líquido nunca fica negativo -- ninguém paga para ter trabalhado. O
        que sobra da perda aparece em "ainda devido", para a conversa
        acontecer com número em cima da mesa.
        """
        for operador in self:
            pedidos = self.env['pos.order'].search([
                ('config_id', '=', operador.pos_config_id.id),
                ('state', '!=', 'cancel'),
            ]) if operador.pos_config_id else self.env['pos.order']
            operador.pos_amount = sum(pedidos.mapped('amount_total'))
            operador.commission_amount = \
                operador.pos_amount * operador.commission_pc / 100.0
            operador.daily_amount = operador.daily_rate * operador.days
            equipe = len(operador.fair_id.cashier_ids) or 1
            # SÓ o que sumiu sob a guarda deles. O exemplar que saiu do
            # depósito e não chegou na praça sumiu na estrada -- não é da
            # conta de quem estava no balcão.
            perda = sum(operador.fair_id.loss_ids.filtered(
                'charged_to_team').mapped('value'))
            operador.loss_share = perda / equipe
            bruto = operador.commission_amount + operador.daily_amount
            operador.net_amount = max(0.0, bruto - operador.loss_share)
            operador.uncovered_loss = max(
                0.0, operador.loss_share - bruto)

    _fair_operator_uniq = models.Constraint(
        'unique(fair_id, partner_id)',
        'Two registers of the same fair cannot have the same operator.')

    @api.depends('partner_id')
    def _compute_name(self):
        for operador in self:
            operador.name = operador.partner_id.name or ''

    @api.depends('partner_id')
    def _compute_user(self):
        for operador in self:
            operador.user_id = operador.partner_id.user_ids[:1]

    @api.depends('user_id', 'access_granted')
    def _compute_access_state(self):
        for operador in self:
            if not operador.user_id:
                operador.access_state = 'no_account'
            elif operador.access_granted:
                operador.access_state = 'granted'
            else:
                operador.access_state = 'ended'

    # ------------------------------------------------------------------
    # o acesso, que nasce com o evento e morre com ele
    # ------------------------------------------------------------------
    ABERTOS = ('planned', 'shipped')

    def _grupos(self):
        """Os grupos que cada papel dá, e a diferença entre eles é grande.

        O ASSISTENTE só tem o caixa. Ele vende no balcão e acabou: não abre a
        feira, não vê grade, não vê perda, não vê outro evento. Dar-lhe o
        aplicativo inteiro seria dar-lhe telas que ele não vai usar e dados
        que não são dele.

        O GERENTE é CIRCUNSTANCIAL, e é aí que a régua mudou. Ele toca o
        evento na praça: entra no caixa das colegas para destravar problema,
        dá desconto acima do praticado, confere carga, conta a mesa, fecha o
        dia e registra perda. Ele NÃO planeja: grade, modelo, remessa e --
        principalmente -- quanto cada um ganha são decisões de quem monta o
        evento, tomadas antes de a feira existir na rua. Por isso ele deixou
        de receber o papel de Administrador de Feiras da casa, que trazia
        tudo isso junto.
        """
        self.ensure_one()
        grupos = self.env.ref('liber_fairs_pos.group_fair_cashier')
        if self.role == 'manager':
            grupos |= self.env.ref('liber_fairs_pos.group_fair_field')
        return grupos

    def _sincronizar_acesso(self):
        """Dá ou tira o acesso conforme o papel e o estado do evento."""
        for operador in self:
            aberto = operador.fair_id.state in operador.ABERTOS
            if aberto and operador.user_id:
                operador._conceder()
            elif operador.access_granted:
                operador._revogar()
        return True

    def _conceder(self):
        self.ensure_one()
        grupos = self._grupos()
        # Só o que FALTA. O que a pessoa já tinha não é dádiva nossa, e por
        # isso não entra na lista do que será tirado depois.
        faltando = grupos - self.user_id.all_group_ids
        if faltando:
            self.user_id.sudo().write(
                {'group_ids': [(4, g.id) for g in faltando]})
        self.sudo().granted_group_ids = [(4, g.id) for g in faltando]
        if not self.access_granted:
            self.sudo().access_granted = True
            self.fair_id.message_post(body=_(
                "%(pessoa)s now has access to %(feira)s as %(papel)s. It ends "
                "when the event comes home.",
                pessoa=self.partner_id.display_name,
                feira=self.fair_id.display_name,
                papel=dict(self._fields['role']._description_selection(
                    self.env))[self.role]))

    def _revogar(self):
        """Tira o acesso, sem tirar de quem o tem por outro caminho.

        Só se remove o vínculo DIRETO. Quem é do Comercial da casa tem o papel
        de Feiras por herança do perfil dele, e essa herança não se toca aqui.
        E quem ainda está escalado em outro evento aberto continua entrando.
        """
        self.ensure_one()
        usuario = self.user_id
        concedidos = self.granted_group_ids
        self.sudo().write({'access_granted': False,
                           'granted_group_ids': [(5, 0, 0)]})
        if not usuario or not concedidos:
            return
        # O que outro evento ABERTO ainda precisa fica; o resto sai.
        outros = self.sudo().search([
            ('id', '!=', self.id),
            ('user_id', '=', usuario.id),
            ('access_granted', '=', True),
            ('fair_id.state', 'in', self.ABERTOS),
        ])
        # O que os outros eventos abertos EXIGEM, e não o que eles receberam:
        # se o primeiro evento deu o PDV, o segundo não recebeu nada (já
        # estava lá) -- e encerrar o primeiro arrancaria o acesso de quem
        # ainda trabalha o segundo.
        precisa = self.env['res.groups']
        for outro in outros:
            precisa |= outro._grupos()
        tirar = concedidos - precisa
        if not tirar:
            return
        usuario.sudo().write({'group_ids': [(3, g.id) for g in tirar]})
        self.fair_id.message_post(body=_(
            "%(pessoa)s no longer has access to the events: %(feira)s came "
            "home.",
            pessoa=self.partner_id.display_name,
            feira=self.fair_id.display_name))

    @api.model_create_multi
    def create(self, vals_list):
        # Os DIAS nascem com a duração do evento: é o caso comum, e corrigir
        # para menos é mais fácil do que lembrar de preencher.
        for vals in vals_list:
            if vals.get('days'):
                continue
            fair = self.env['event.fair'].browse(vals.get('fair_id'))
            if fair.date_start and fair.date_end:
                vals['days'] = (fair.date_end - fair.date_start).days + 1
        linhas = super().create(vals_list)
        linhas._sincronizar_acesso()
        return linhas

    # O que se combina com quem trabalha o evento. Enquanto o evento é
    # rascunho não há evento: não há grade, nem dias, nem analítico onde a
    # despesa caia. Combinar comissão antes disso é combinar no vazio.
    _DINHEIRO = ('commission_pc', 'daily_rate', 'days')

    def write(self, vals):
        self._exigir_quem_planeja(vals)
        self._exigir_o_planejamento(vals)
        res = super().write(vals)
        if {'role', 'partner_id'} & set(vals):
            self._sincronizar_acesso()
        if 'role' in vals:
            # Virou gerente, pode digitar desconto; voltou a operador, não
            # pode. A chave do desconto acompanha o papel.
            self.fair_id._sincronizar_desconto()
        return res

    def _exigir_quem_planeja(self, vals):
        """Quanto cada um ganha é de quem PLANEJA o evento.

        O gerente de campo é circunstancial: ele toca a feira na praça, entra
        no caixa das colegas, dá desconto, conta a mesa e registra perda. O
        que ele não faz é decidir a própria remuneração nem a dos outros --
        seria juiz em causa própria, e a combinação é anterior ao evento.

        A aba fica escondida para ele, e isto é a tranca: aba escondida não
        impede escrita por outro caminho.
        """
        if not set(vals) & set(self._DINHEIRO):
            return
        if self.env.su or self.env.user.has_group(
                'liber_fairs.group_fair_manager'):
            return
        raise UserError(_(
            "Commission and daily rate are agreed by whoever plans the "
            "event. Talk to the person who put the team together."))

    def _exigir_o_planejamento(self, vals):
        """Comissão e diária só depois do Planejar.

        É o Planejar que cria a localização da feira, monta os dias e abre o
        analítico do evento -- e o número de dias de cada um nasce dali. Antes
        disso o evento é uma intenção, e o que se combinasse aqui ficaria
        pendurado num evento que ainda pode não acontecer.
        """
        if not set(vals) & set(self._DINHEIRO):
            return
        rascunho = self.filtered(lambda o: o.fair_id.state == 'draft')
        if rascunho:
            raise UserError(_(
                "Plan %(feira)s first: commission and daily rate are agreed "
                "on a planned event, which is the one that already has its "
                "days and its analytic account.",
                feira=rascunho[0].fair_id.display_name))

    def unlink(self):
        for operador in self.filtered('access_granted'):
            operador._revogar()
        return super().unlink()
