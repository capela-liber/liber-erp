# -*- coding: utf-8 -*-
"""A feira: a unidade que agrega tudo o que sai, vende e volta de um evento.

Feira não é venda: é remessa temporária. O estoque sai da editora, fica dias
sob a guarda de outra pessoa, vende em parte num PDV que não é o ERP, e volta
incompleto. Passar isso pelo fluxo de venda comum baixa estoque no envio,
reconhece receita antes de existir venda e não deixa rastro entre o que foi, o
que vendeu e o que voltou.

Este arquivo cobre as fases 1 e 2 de _mds/modulo-eventos-feiras.md: o evento
com sequência E e calendário, e a localização virtual com tipos de operação
próprios. O fiscal (§3.4), o template de grade (§3.5), o CSV do PDV (§3.6), o
faturamento (§3.7) e o painel (§3.9) ainda não estão aqui.
"""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EventFair(models.Model):
    _name = 'event.fair'
    _description = 'Fair / Event'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(string='Name', required=True, tracking=True)
    code = fields.Char(
        string='Reference', required=True, readonly=True, copy=False,
        index=True, default=lambda self: _('New'),
        help="E00001. The number that names the fair's stock location and "
             "every document of the event.")
    # UMA FEIRA, UMA EMPRESA (decidido em 08/09/2026).
    #
    # Havia aqui um campo "Selos", lista de empresas participantes, herdado
    # da ideia de um evento com títulos de vários selos. Era informativo e
    # não fazia nada: o armazém de onde a carga sai, a localização, a posição
    # fiscal e a nota são todos de UMA empresa. Ele prometia uma feira
    # multi-selo que o resto do módulo não entregava.
    #
    # A decisão fecha o ponto em aberto 4 da especificação: evento com
    # títulos de mais de um selo são DUAS feiras, uma por empresa, cada uma
    # com a sua remessa e a sua nota. É o que a nota fiscal já exigia -- ela
    # sai de um CNPJ, não de um evento.
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)

    # O período do evento. Houve aqui uma segunda camada de datas, a "janela
    # logística" (envio -> retorno), pensada para medir a ocupação do acervo
    # entre feiras. Saiu em 08/09/2026 a pedido do dono: duas datas que
    # ninguém preenchia e nada consumia são duas perguntas a mais na tela.
    # A data programada das transferências passa a ser a do despacho.
    date_start = fields.Date(string='Start', required=True, tracking=True)
    date_end = fields.Date(string='End', required=True, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string='Organiser', tracking=True,
        help="Who runs the event, or answers for the table.")
    # O responsável NASCE do que a casa decidiu nas Definições, e se muda
    # aqui quando o evento pede outra pessoa. Sem o padrão, cada evento
    # nascia no nome de quem clicou, que raramente é quem responde.
    responsible_id = fields.Many2one(
        'res.users', string='Responsible', tracking=True,
        default=lambda self: self._default_responsible(),
        help="Who answers for the stock in the field. Starts as the events "
             "responsible set in Settings, and can be changed per event.")
    # O ANALÍTICO do evento: é ele que junta, num lugar só, o que o evento
    # custou (diária, comissão, montagem) e o que ele deu. Nasce sozinho na
    # primeira vez que se precisa dele, com o código do evento.
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic account', copy=False,
        help="Where this event gathers cost and revenue. Created on the "
             "first use if left empty.")
    location = fields.Char(
        string='Place', help="Where the event happens: city, venue, address.")
    # A feira é um CANAL, ao lado da Amazon, da distribuição e da loja
    # própria. Sem o canal de vendas preenchido, o evento não aparece nos
    # relatórios comerciais como canal, e a pergunta "quanto a feira nos deu
    # este ano?" não tem onde ser respondida. O campo é o gancho; o painel
    # do §3.9 é quem vai consumi-lo.
    #
    # Houve aqui um segundo campo, `channel_type` (Feira do livro / Evento
    # próprio / Consignação de evento / Lançamento). Saiu em 08/09/2026: dois
    # campos chamados "Canal" um embaixo do outro, e só um deles conversava
    # com o resto do sistema. Tipo de evento, se voltar a fazer falta, é
    # etiqueta -- não uma segunda taxonomia paralela à comercial.
    team_id = fields.Many2one(
        'crm.team', string='Sales Channel', tracking=True,
        default=lambda self: self._default_team_id(),
        help="Which sales channel this event reports into.")

    state = fields.Selection(
        # "Em curso" saiu em 08/09/2026: a única porta para ele era um botão
        # Começar que não mudava nada, e "Enviado" já diz o que importa --
        # os livros saíram e ainda não voltaram.
        [('draft', 'Draft'),
         ('planned', 'Planned'),
         ('shipped', 'Shipped'),
         ('returned', 'Returned'),
         ('settled', 'Settled'),
         ('closed', 'Closed')],
        string='Status', default='draft', required=True, tracking=True)

    # QUEM PLANEJA, e não quem está na praça. O gerente de campo é
    # circunstancial: ele toca o evento na rua e não decide o que vai nem
    # quanto cada um ganha. A tela precisa saber a diferença, e `groups=` num
    # botão não serve para trancar um campo dentro de uma aba.
    # A REMESSA DE VOLTA JÁ PEDIDA. O evento continua "Enviado" até a
    # mercadoria sair da mesa, e sem este campo o botão Retorno seguia
    # clicável -- um segundo clique criaria uma segunda remessa dos MESMOS
    # livros, porque a mesa ainda os tem.
    return_pending = fields.Boolean(
        string='Return waiting to be packed',
        compute='_compute_return_pending')

    @api.depends('picking_ids.state', 'picking_ids.fair_operation')
    def _compute_return_pending(self):
        for fair in self:
            fair.return_pending = bool(fair._pendencia_de_retorno())

    is_fair_planner = fields.Boolean(
        string='Plans events', compute='_compute_is_fair_planner')

    @api.depends_context('uid')
    def _compute_is_fair_planner(self):
        pode = self.env.user.has_group('liber_fairs.group_fair_manager')
        for fair in self:
            fair.is_fair_planner = pode

    line_ids = fields.One2many(
        'event.fair.line', 'fair_id', string='Grid', copy=True)
    day_ids = fields.One2many(
        'event.fair.day', 'fair_id', string='Days')
    day_count = fields.Integer(compute='_compute_day_count')
    loss_ids = fields.One2many('event.fair.loss', 'fair_id', string='Losses')
    loss_count = fields.Integer(compute='_compute_loss_count')
    loss_value = fields.Float(
        string='Loss value', digits='Product Price',
        compute='_compute_loss_count')

    # O trânsito É DESTA FEIRA, e isso custou caro para aprender. Com o
    # trânsito genérico da empresa, a chegada de um retorno encontrava lá
    # dentro livro de outra operação, ficava "Pronto" com o que não era dela,
    # e validar fechou uma volta de 107 exemplares com 8 -- os 99 restantes
    # viraram perda. Carga de feira não divide corredor com ninguém.
    transit_location_id = fields.Many2one(
        'stock.location', string='Transit', readonly=True, copy=False,
        help="Where this fair's load sits between the warehouse and the "
             "table. One per fair: a leg of this fair never reserves stock "
             "that belongs to another operation.")
    stock_location_id = fields.Many2one(
        'stock.location', string='Fair Location', readonly=True, copy=False,
        help="The virtual location holding this fair's stock. Created when "
             "the fair is planned; its balance is what is physically on the "
             "table right now.")
    picking_ids = fields.One2many(
        'stock.picking', 'fair_id', string='Transfers')
    picking_count = fields.Integer(compute='_compute_picking_count')

    qty_planned = fields.Float(
        string='Planned', compute='_compute_qty', digits='Product Unit')
    qty_sent = fields.Float(
        string='Sent', compute='_compute_qty', digits='Product Unit')
    qty_returned = fields.Float(
        string='Returned', compute='_compute_qty', digits='Product Unit')
    qty_sold = fields.Float(
        string='Sold', compute='_compute_qty', digits='Product Unit')
    qty_lost = fields.Float(
        string='Lost', compute='_compute_qty', digits='Product Unit')
    qty_on_shelf = fields.Float(
        string='On the table', compute='_compute_qty', digits='Product Unit')

    # v19: `_sql_constraints` não é mais suportado -- é models.Constraint.
    _code_company_uniq = models.Constraint(
        'unique(code, company_id)',
        'The fair reference must be unique per company.')

    # ------------------------------------------------------------------
    # básico
    # ------------------------------------------------------------------
    @api.model
    def _default_team_id(self):
        """O canal de eventos da empresa, se houver um com essa cara.

        Não cria canal nenhum: canal de vendas é cadastro do comercial, e
        inventar um pelas costas dele encheria a lista de equipes de cada
        empresa com uma "Feiras" que ninguém pediu. Se não achar, fica vazio
        e a pessoa escolhe.
        """
        company = self.env.company
        return self.env['crm.team'].search([
            ('company_id', 'in', [company.id, False]),
            '|', ('name', 'ilike', 'feira'), ('name', 'ilike', 'event'),
        ], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                company = vals.get('company_id') or self.env.company.id
                # sudo DELIBERADO: o número da feira é infraestrutura, não
                # um registro que a pessoa escolhe. Sem ele, quem tem só o
                # papel de Feiras leva AccessError em ir.sequence ao abrir a
                # primeira feira -- e o papel de Feiras existe justamente
                # para quem não opera Inventário nem Contabilidade.
                vals['code'] = self.env['ir.sequence'].sudo().with_company(
                    company).next_by_code('event.fair') or _('New')
        return super().create(vals_list)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for fair in self:
            fair.display_name = '[%s] %s' % (fair.code, fair.name or '')

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for fair in self:
            if fair.date_end < fair.date_start:
                raise UserError(_("The fair cannot end before it starts."))

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for fair in self:
            fair.picking_count = len(fair.picking_ids)

    @api.depends('loss_ids.qty', 'loss_ids.value')
    def _compute_loss_count(self):
        for fair in self:
            fair.loss_count = len(fair.loss_ids)
            fair.loss_value = sum(fair.loss_ids.mapped('value'))

    @api.depends('day_ids')
    def _compute_day_count(self):
        for fair in self:
            fair.day_count = len(fair.day_ids)

    @api.depends('line_ids.qty_planned', 'line_ids.qty_sent',
                 'line_ids.qty_returned', 'line_ids.qty_sold',
                 'line_ids.qty_lost')
    def _compute_qty(self):
        for fair in self:
            lines = fair.line_ids
            fair.qty_planned = sum(lines.mapped('qty_planned'))
            fair.qty_sent = sum(lines.mapped('qty_sent'))
            fair.qty_returned = sum(lines.mapped('qty_returned'))
            fair.qty_sold = sum(lines.mapped('qty_sold'))
            fair.qty_lost = sum(lines.mapped('qty_lost'))
            fair.qty_on_shelf = sum(lines.mapped('qty_on_shelf'))

    # ------------------------------------------------------------------
    # localização
    # ------------------------------------------------------------------
    @api.model
    def _default_responsible(self):
        company = self.env.company
        return company.fair_manager_id or self.env.user

    def _get_analytic_account(self):
        """O analítico do evento, criado na primeira vez que se precisa dele.

        Nasce com o código e o nome do evento, no plano que as Definições
        mandam. Sem plano configurado, não se inventa um: avisa-se, porque
        plano de analítico é decisão de quem cuida do plano de contas.
        """
        self.ensure_one()
        if self.analytic_account_id:
            return self.analytic_account_id
        plano = self.company_id.fair_analytic_plan_id
        if not plano:
            raise UserError(_(
                "Set the analytic plan for events in Settings first: the "
                "event has no place to gather what it cost and what it "
                "gave."))
        conta = self.env['account.analytic.account'].sudo().create({
            'name': '%s %s' % (self.code, self.name),
            'plan_id': plano.id,
            'company_id': self.company_id.id,
        })
        self.sudo().analytic_account_id = conta.id
        return conta

    def _get_stock_location(self):
        """A localização da feira, criada na primeira vez que se precisa dela.

        sudo DELIBERADO, mesmo motivo da raiz (ver stock_location): criar
        stock.location é direito de Inventário, e quem planeja uma feira é do
        Comercial. Os valores são todos daqui -- nome, pai, empresa -- e
        nenhum vem da tela.
        """
        self.ensure_one()
        if not self.stock_location_id:
            root = self.env['stock.location']._fair_root(self.company_id)
            location = self.env['stock.location'].sudo().create({
                'name': self.code,
                'usage': 'internal',
                'location_id': root.id,
                'company_id': self.company_id.id,
                'is_fair_location': True,
                'fair_id': self.id,
            })
            self.sudo().stock_location_id = location.id
        return self.stock_location_id

    def _get_transit_location(self):
        """O corredor desta feira, criado na primeira vez que se precisa dele.

        Feira que JÁ TEM movimento continua no trânsito antigo: trocar o
        corredor no meio da viagem partiria a corrente entre a perna que saiu
        e a que ainda não chegou, e deixaria carga parada num lugar que
        ninguém mais consulta.
        """
        self.ensure_one()
        if self.transit_location_id:
            return self.transit_location_id
        if self.picking_ids:
            return self.company_id._fair_transit_location()
        root = self.env['stock.location']._fair_root(self.company_id)
        location = self.env['stock.location'].sudo().create({
            'name': _('%s (transit)', self.code or self.name),
            'usage': 'transit',
            'location_id': root.id,
            'company_id': self.company_id.id,
        })
        self.sudo().transit_location_id = location.id
        return location

    def _warehouse_location(self):
        self.ensure_one()
        warehouse = self.company_id._fair_warehouse()
        if not warehouse:
            raise UserError(_(
                "Company %s has no warehouse to ship the fair from.",
                self.company_id.display_name))
        return warehouse.lot_stock_id

    # ------------------------------------------------------------------
    # movimentos
    # ------------------------------------------------------------------
    def _create_fair_picking(self, operation, quantities, scheduled_date=None,
                             source=None):
        """Um picking da feira. `quantities` é {product: qty}, tudo positivo.

        Todo movimento da feira passa por aqui, e é sempre stock.picking /
        stock.move -- nunca escrita direta em stock.quant. É o que dá o rastro
        entre o que foi, o que vendeu e o que voltou.
        """
        self.ensure_one()
        quantities = {p: q for p, q in quantities.items() if q > 0}
        if not quantities:
            raise UserError(_("Nothing to move: every quantity is zero."))
        fair_location = self._get_stock_location()
        warehouse_location = self._warehouse_location()
        company = self.company_id
        if operation == 'shipment':
            picking_type = company._get_fair_shipment_operation_type()
            # A ida tem DUAS pernas, e o meio delas é o trânsito.
            #
            # Numa perna só, o instante em que o depósito valida é o instante
            # em que o sistema jura que o livro está na mesa em Santos -- e
            # ele pode estar na estrada, ou em lugar nenhum. Quem garante que
            # chegou é quem está na feira, e é por isso que existe a segunda
            # perna: FEIRA/REC, conferida na praça.
            src, dest = warehouse_location, self._get_transit_location()
        elif operation == 'receipt':
            picking_type = company._get_fair_receipt_operation_type()
            src, dest = self._get_transit_location(), fair_location
        elif operation == 'return_dispatch':
            picking_type = company._get_fair_return_dispatch_operation_type()
            src, dest = fair_location, self._get_transit_location()
        elif operation == 'return':
            picking_type = company._get_fair_return_operation_type()
            src, dest = self._get_transit_location(), warehouse_location
        elif operation == 'sale':
            picking_type = company._get_fair_sale_operation_type()
            src = fair_location
            dest = self.env.ref('stock.stock_location_customers')
        elif operation == 'loss':
            picking_type = company._get_fair_loss_operation_type()
            src = fair_location
            dest = company._fair_scrap_location()
        else:
            raise UserError(_("Unknown fair operation: %s", operation))

        # `source` existe para UM caso: o exemplar que a conferência acusou
        # como falta e ficou parado no TRÂNSITO. Quando alguém finalmente diz
        # o que houve com ele, a baixa tem de sair de onde ele está, e não da
        # mesa -- que talvez nunca o tenha recebido, ou já tenha sido
        # desmontada. Fora disso, a origem é a do próprio movimento.
        if source:
            src = source

        moves = []
        for product, qty in quantities.items():
            moves.append((0, 0, {
                # v19: stock.move não tem mais `name`; o rótulo da linha é
                # `description_picking`.
                'description_picking': product.display_name,
                'product_id': product.id,
                'product_uom_qty': qty,
                'product_uom': product.uom_id.id,
                'location_id': src.id,
                'location_dest_id': dest.id,
                'company_id': company.id,
            }))
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': src.id,
            'location_dest_id': dest.id,
            'partner_id': self.partner_id.id or False,
            'origin': self.code,
            'company_id': company.id,
            'fair_id': self.id,
            'fair_operation': operation,
            'scheduled_date': scheduled_date or fields.Datetime.now(),
            'move_ids': moves,
        })
        picking.action_confirm()
        picking._avisar_de_qual_feira(self, operation)
        return picking

    def _create_shipment_with_receipt(self, quantities):
        """A ida inteira: a saída do armazém e a entrada na feira, encadeadas.

        As duas nascem juntas, e a segunda fica ESPERANDO a primeira -- é o
        encadeamento do próprio Odoo (`move_dest_ids`), o mesmo de uma
        entrega em duas etapas. Quem está na praça abre a FEIRA/REC e confere
        o que chegou; até ele fazer isso, a mercadoria está em trânsito, e
        não na mesa.
        """
        self.ensure_one()
        saida = self._create_fair_picking('shipment', quantities)
        entrada = self._create_fair_picking('receipt', quantities)
        por_produto = {}
        for move in entrada.move_ids:
            por_produto.setdefault(move.product_id, move)
        for move in saida.move_ids:
            destino = por_produto.get(move.product_id)
            if destino:
                move.move_dest_ids = [(4, destino.id)]
        # A entrada passa a "aguardando outra operação": ela não pode ficar
        # pronta antes de a carga sair do armazém. `_recompute_state` é o que
        # faz o Odoo reler a corrente -- só escrever o procure_method deixa o
        # estado velho, e a entrada aparece pronta para conferir uma carga
        # que ainda está na prateleira do depósito.
        entrada.move_ids.write({'procure_method': 'make_to_order'})
        entrada.move_ids._recompute_state()
        return saida, entrada

    # ------------------------------------------------------------------
    # transições
    # ------------------------------------------------------------------
    def action_plan(self):
        for fair in self:
            # O analítico nasce junto com o plano do evento: a partir daqui
            # tudo o que ele custar tem onde cair.
            if fair.company_id.fair_analytic_plan_id \
                    and not fair.analytic_account_id:
                fair._get_analytic_account()
            if not fair.line_ids:
                raise UserError(_(
                    "Fair %s has no grid: there is nothing to send.",
                    fair.display_name))
            fair._get_stock_location()
            fair._build_days()
            fair.state = 'planned'
        return True

    def action_ship(self):
        """A remessa: manda o que foi planejado e ainda não saiu.

        Pode ser chamada mais de uma vez. Evento de vários dias pede REPOSIÇÃO
        no meio: aumenta-se a quantidade planejada da linha (ou soma-se linha
        nova) e clica-se aqui de novo -- sai um segundo picking com a
        diferença, contra a MESMA localização. Uma feira, N remessas, um
        saldo só.
        """
        pickings = self.env['stock.picking']
        for fair in self:
            if fair.state in ('returned', 'settled', 'closed'):
                raise UserError(_(
                    "Fair %s is already back: it cannot be shipped again.",
                    fair.display_name))
            # Desconta o que já foi E o que está A CAMINHO.
            #
            # Só com o "já foi" (que conta movimento CONCLUÍDO), apertar
            # Despachar duas vezes antes de o armazém validar a primeira
            # carga manda tudo de novo: a segunda transferência nasce com a
            # grade inteira, e a feira recebe em dobro. Ele apertou duas
            # vezes e viu.
            pending = {
                line.product_id: (line.qty_planned - line.qty_sent
                                  - line.qty_requested)
                for line in fair.line_ids
            }
            if not any(qty > 0 for qty in pending.values()):
                a_caminho = sum(fair.line_ids.mapped('qty_requested'))
                if a_caminho:
                    raise UserError(_(
                        "Everything planned for %(feira)s is already on its "
                        "way (%(qtd)s copies, still to be validated by the "
                        "warehouse). Raise a planned quantity to send more.",
                        feira=fair.display_name, qtd=int(a_caminho)))
                raise UserError(_(
                    "Everything planned for %s has already been shipped. "
                    "Raise a planned quantity to send a replenishment.",
                    fair.display_name))
            saida, entrada = fair._create_shipment_with_receipt(pending)
            pickings |= saida
            if fair.state == 'planned':
                fair.state = 'shipped'
        return pickings

    def action_return(self):
        """Devolve tudo o que a mesa tem, sem conferência.

        A conferência não acontece aqui: acontece na CHEGADA, em Recebimentos,
        onde quem recebe dá o ok. No meio de uma feira ninguém para para
        classificar avaria título a título -- registra-se o que faltou, e a
        explicação vem depois em Perdas.
        """
        pickings = self.env['stock.picking']
        for fair in self:
            if fair.state != 'shipped':
                raise UserError(_(
                    "Fair %s is not out to be returned.", fair.display_name))
            pendente = fair._pendencia_de_retorno()
            if pendente:
                raise UserError(_(
                    "%(feira)s already has a return waiting to be packed "
                    "(%(mov)s). Validate it — a second one would ask for the "
                    "same copies twice.",
                    feira=fair.display_name,
                    mov=', '.join(pendente.mapped('name'))))
            fair._close_open_days()
            devolvendo = {
                line.product_id: line.qty_on_shelf
                for line in fair.line_ids if line.qty_on_shelf > 0
            }
            pickings |= fair._do_return(devolvendo, [])
        return pickings

    def _do_return(self, devolvendo, perdas):
        """A volta inteira: o que se devolve e o que se dá por perdido.

        `devolvendo` é {produto: quantidade}; `perdas` é uma lista de
        (produto, quantidade, motivo). Juntos têm de esvaziar a mesa: é essa
        soma que faz a feira poder fechar. O que não voltou e não foi
        classificado seria exemplar que o sistema perdeu de vista.

        A volta também tem duas pernas. A praça embala e despacha (FEIRA/RET,
        mesa -> trânsito), e o ARMAZÉM confere o que chegou (FEIRA/IN,
        trânsito -> estoque). A segunda perna é a conferência do lado de cá:
        se o armazém receber menos do que a praça mandou, a diferença fica
        parada no trânsito, visível, em vez de virar zero silencioso.
        """
        self.ensure_one()
        pickings = self.env['stock.picking']
        devolvendo = {p: q for p, q in (devolvendo or {}).items() if q > 0}
        if devolvendo:
            pickings |= self._create_fair_picking('return_dispatch', devolvendo)
        pickings |= self._registrar_perdas(perdas)
        # A CHEGADA NASCE DEPOIS, quando a mercadoria sai da mesa de verdade
        # (ver `_abrir_a_chegada_do_retorno`). E o evento só vira RETORNADO
        # nessa mesma hora.
        self._talvez_retornado()
        return pickings

    def _pendencia_de_retorno(self):
        """As remessas de volta que ainda não saíram da mesa."""
        self.ensure_one()
        return self.picking_ids.filtered(
            lambda p: p.fair_operation == 'return_dispatch'
            and p.state not in ('done', 'cancel'))

    def _talvez_retornado(self):
        """O evento volta quando a MERCADORIA volta, e não quando se pede.

        Pedir o retorno cria a remessa de volta; a mesa continua cheia até
        alguém embalar e validar. Gravar `returned` no clique deixava a ficha
        dizendo que acabou enquanto trinta e quatro exemplares seguiam na
        praça -- e o estoque do armazém, trinta e quatro menor, com razão.
        Foi o que o dono viu: "o estoque da loja não batia com o estoque na
        EV".
        """
        for fair in self:
            if fair.state == 'returned' or fair._pendencia_de_retorno():
                continue
            fair.state = 'returned'
            fair._ao_retornar()

    def _ao_retornar(self):
        """Gancho do momento em que o evento fecha de fato.

        Aqui não faz nada; as pontes penduram o que é delas (arquivar os
        caixas, deixar as contas da equipe prontas). Existe para que esse
        trabalho aconteça QUANDO A MERCADORIA VOLTA, e não quando alguém
        aperta o botão de pedir.
        """
        return True

    def _abrir_a_chegada_do_retorno(self, saida):
        """A segunda perna da volta: trânsito -> armazém.

        Ela nasce só agora, com a remessa de volta já validada, e por dois
        motivos:

          - o armazém não pode ver na bancada um cartão VERMELHO de carga que
            ainda está a seiscentos quilômetros, esperando ser embalada;
          - nascendo junto com a remessa, ela reservava o que encontrasse no
            trânsito -- inclusive o exemplar que saiu do depósito e nunca
            chegou na mesa, que já estava contado como falta. A chegada do
            retorno ia receber um livro que a feira nunca teve.

        O que ela pede é O QUE SAIU, medido no movimento concluído.
        """
        self.ensure_one()
        quantidades = {}
        for move in saida.move_ids.filtered(lambda m: m.state == 'done'):
            if move.quantity > 0:
                quantidades.setdefault(move.product_id, 0.0)
                quantidades[move.product_id] += move.quantity
        if not quantidades:
            return self.env['stock.picking']
        entrada = self._create_fair_picking('return', quantidades)
        por_produto = {m.product_id: m for m in entrada.move_ids}
        for move in saida.move_ids:
            destino = por_produto.get(move.product_id)
            if destino:
                move.move_dest_ids = [(4, destino.id)]
        entrada.move_ids.write({'procure_method': 'make_to_order'})
        entrada.move_ids._recompute_state()
        return entrada

    def _registrar_perdas(self, perdas, stage='fair'):
        """Tira da mesa o que não volta, e guarda por quê."""
        self.ensure_one()
        from .event_fair_loss import DESTINO
        pickings = self.env['stock.picking']
        por_destino = {}
        for produto, qty, motivo in (perdas or []):
            if qty <= 0 or motivo not in DESTINO:
                # "Não recebido" não move estoque: o exemplar nunca chegou.
                continue
            por_destino.setdefault(DESTINO[motivo], {}).setdefault(
                motivo, {}).setdefault(produto, 0.0)
            por_destino[DESTINO[motivo]][motivo][produto] += qty
        for operacao, por_motivo in por_destino.items():
            quantidades = {}
            for motivo, produtos in por_motivo.items():
                for produto, qty in produtos.items():
                    quantidades.setdefault(produto, 0.0)
                    quantidades[produto] += qty
            picking = self._create_fair_picking(operacao, quantidades)
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.with_context(
                skip_backorder=True,
                picking_ids_not_to_backorder=picking.ids).button_validate()
            pickings |= picking
            for motivo, produtos in por_motivo.items():
                self.env['event.fair.loss'].create([{
                    'fair_id': self.id,
                    'product_id': produto.id,
                    'qty': qty,
                    'reason': motivo,
                    'stage': stage,
                    'picking_id': picking.id,
                } for produto, qty in produtos.items()])
        return pickings

    def _close_open_days(self):
        """Feira que voltou não deixa dia aberto para trás.

        Dia ainda aberto na hora do retorno é dia que ninguém fechou -- a
        praça esvaziou, a van saiu, e a contagem daquele dia não vai
        acontecer mais. Deixá-lo aberto guarda uma pergunta que não tem mais
        resposta possível, e faz a lista de fechamentos mentir sobre o que
        falta fazer.

        O que NÃO se faz aqui é inventar contagem: dia sem contagem fecha
        vazio, e o que ele deixou de registrar aparece na diferença do
        retorno, que é onde essa conversa tem de acontecer. E nenhuma
        reposição sai deste caminho: a feira acabou, mandar livro para uma
        praça vazia seria o pior tipo de automatismo.
        """
        for fair in self:
            for day in fair.day_ids.filtered(lambda d: d.state == 'draft'):
                day.line_ids.write({'qty_replenish': 0.0})
                if any(line.qty_sold for line in day.line_ids):
                    day.action_close()
                else:
                    day.state = 'closed'
        return True

    def action_draft(self):
        for fair in self:
            if fair.picking_ids.filtered(lambda p: p.state == 'done'):
                raise UserError(_(
                    "Fair %s already moved stock: it cannot go back to draft.",
                    fair.display_name))
            fair.picking_ids.filtered(
                lambda p: p.state != 'cancel').action_cancel()
            fair.state = 'draft'
        return True

    # ------------------------------------------------------------------
    # dias
    # ------------------------------------------------------------------
    def _build_days(self):
        """Um registro por dia do evento -- o fechamento diário mora neles."""
        Day = self.env['event.fair.day']
        for fair in self:
            existing = set(fair.day_ids.mapped('date'))
            day = fair.date_start
            vals = []
            while day <= fair.date_end:
                if day not in existing:
                    vals.append({'fair_id': fair.id, 'date': day})
                day += timedelta(days=1)
            if vals:
                Day.create(vals)
        return True

    # ------------------------------------------------------------------
    # ações de tela
    # ------------------------------------------------------------------
    def action_view_pickings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fair Transfers'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('fair_id', '=', self.id)],
            'context': {'default_fair_id': self.id},
        }

    def action_view_losses(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fair Losses'),
            'res_model': 'event.fair.loss',
            'view_mode': 'list,form',
            'domain': [('fair_id', '=', self.id)],
        }

    def action_view_days(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Daily Closings'),
            'res_model': 'event.fair.day',
            'view_mode': 'list,form',
            'domain': [('fair_id', '=', self.id)],
            'context': {'default_fair_id': self.id},
        }
