# -*- coding: utf-8 -*-
"""O fechamento diário: no fim do dia conta-se a mesa, e a conta fecha sozinha.

Evento de vários dias não se apura só no fim. Todo dia, quando a praça fecha,
quem está lá conta o que sobrou na mesa e lança aqui. O sistema não pergunta o
que vendeu: ele DEDUZ, porque sabe o que estava na mesa na abertura e o que
entrou de reposição no meio:

    vendido no dia = saldo na abertura + reposição do dia − contagem do fim

Fechar o dia gera o movimento "Venda Feira" (mesa → Clientes) com essa
diferença, e por isso o saldo da localização volta a bater com a mesa física
todo fim de dia -- em vez de só bater no acerto final, semanas depois.

O DINHEIRO não passa por aqui. O CSV do PDV (§3.6) e a fatura (§3.7) são as
fases 5 e 6: quando chegarem, é contra este número diário que o extrato da
maquininha vai ser conferido, e a divergência aparece no dia em que nasceu, e
não somada e indecifrável no fim.
"""
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EventFairDay(models.Model):
    _name = 'event.fair.day'
    _description = 'Fair Daily Closing'
    _order = 'fair_id, date'

    fair_id = fields.Many2one(
        'event.fair', string='Fair', required=True, ondelete='cascade',
        index=True)
    company_id = fields.Many2one(related='fair_id.company_id', store=True)
    # Gravado: filtro e coluna só funcionam em campo que está no banco, e
    # esta lista junta os dias de TODAS as feiras -- sem saber em que pé
    # está a feira de cada linha, ela é um monte.
    fair_state = fields.Selection(
        related='fair_id.state', string='Fair Status', store=True)
    date = fields.Date(string='Day', required=True)
    state = fields.Selection(
        [('draft', 'Open'), ('closed', 'Closed')],
        string='Status', default='draft', required=True)
    line_ids = fields.One2many(
        'event.fair.day.line', 'day_id', string='Count')
    picking_id = fields.Many2one(
        'stock.picking', string='Sale Transfer', readonly=True, copy=False,
        help="The stock move this closing generated.")
    # O que ESTE dia pediu. Não é botão na tela: havia dois lá, "A caminho" e
    # "Reposições", e no instante em que se fecha o dia os dois apontam para a
    # mesma transferência -- divergem só depois que a carga chega. Dois botões
    # que dizem a mesma coisa quase sempre é um botão a mais.
    #
    # O vínculo continua aqui porque é ele que impede pedir duas vezes, e o
    # caminho de volta não se perdeu: a transferência carrega `fair_day_id` e
    # o documento de origem diz de que dia veio.
    replenish_picking_ids = fields.Many2many(
        'stock.picking', 'event_fair_day_replenish_rel', 'day_id',
        'picking_id', string='Replenishments', readonly=True, copy=False)
    replenish_count = fields.Integer(compute='_compute_replenish')
    # "A caminho" era um número sem porta: dizia que faltava chegar e não
    # dizia por onde. Daqui se abre a transferência, que é onde está a
    # resposta que interessa a quem está na praça -- saiu? quando chega?
    in_transit_picking_ids = fields.Many2many(
        'stock.picking', string='On the way',
        compute='_compute_in_transit')
    in_transit_count = fields.Integer(compute='_compute_in_transit')
    qty_replenish = fields.Float(
        string='To replenish', digits='Product Unit',
        compute='_compute_replenish')
    # LACRADO: a feira voltou, e o que este dia registrou não se mexe mais.
    # Fechar um dia é dizer "a contagem de hoje está feita"; lacrar é dizer
    # "esta feira acabou". Enquanto a feira roda, um dia fechado ainda aceita
    # pedido de reposição -- o dia fecha às onze da noite e a reposição do dia
    # seguinte às vezes se decide depois. Depois que a mercadoria volta não há
    # praça para onde mandar, e deixar o botão ali só produz erro.
    is_sealed = fields.Boolean(
        string='Sealed', compute='_compute_is_sealed',
        help="The fair has come back: this day is history now.")
    qty_sold = fields.Float(
        string='Sold', digits='Product Unit', compute='_compute_qty_sold',
        store=True)
    note = fields.Text(string='Notes')

    _fair_date_uniq = models.Constraint(
        'unique(fair_id, date)', 'A fair has one closing per day.')

    @api.depends('line_ids.qty_sold')
    def _compute_qty_sold(self):
        for day in self:
            day.qty_sold = sum(day.line_ids.mapped('qty_sold'))

    @api.depends('fair_id.picking_ids.state',
                 'fair_id.picking_ids.fair_operation')
    def _compute_in_transit(self):
        """As remessas desta feira que saíram e ainda não chegaram.

        Não só as que ESTE dia pediu: o que interessa a quem conta a mesa é
        tudo o que está na estrada para ela, tenha sido pedido no fechamento
        de ontem ou despachado direto da feira.
        """
        for day in self:
            a_caminho = day.fair_id.picking_ids.filtered(
                lambda p: p.fair_operation == 'shipment'
                and p.state not in ('done', 'cancel'))
            day.in_transit_picking_ids = a_caminho
            day.in_transit_count = len(a_caminho)

    @api.depends('fair_id.state')
    def _compute_is_sealed(self):
        for day in self:
            day.is_sealed = day.fair_id.state in (
                'returned', 'settled', 'closed')

    @api.depends('line_ids.qty_replenish', 'replenish_picking_ids')
    def _compute_replenish(self):
        for day in self:
            day.qty_replenish = sum(day.line_ids.mapped('qty_replenish'))
            day.replenish_count = len(day.replenish_picking_ids)

    @api.depends('fair_id')
    def _compute_display_name(self):
        for day in self:
            day.display_name = '%s — %s' % (
                day.fair_id.code or '', day.date or '')

    def action_fill(self):
        """Traz para a contagem tudo o que deveria estar na mesa.

        Já vem com a contagem IGUAL ao esperado: quem conta corrige para baixo
        o que vendeu. É menos digitação num balcão de feira, com o celular na
        mão, do que digitar título a título o que saiu.
        """
        for day in self:
            if day.state == 'closed':
                raise UserError(_("Day %s is already closed.", day.date))
            day.line_ids.unlink()
            vals = []
            for line in day.fair_id.line_ids:
                # Título que NUNCA foi para a feira não está na mesa e não
                # entra na contagem. Título que foi e ESGOTOU entra, com
                # zero: é justamente ele que se quer repor, e sumir da lista
                # obrigaria a pessoa a lembrar de cabeça o que acabou. O zero
                # na mesa é informação, não ruído.
                if line.qty_sent <= 0:
                    continue
                vals.append({
                    'day_id': day.id,
                    'product_id': line.product_id.id,
                    'qty_expected': line.qty_on_shelf,
                    'qty_counted': line.qty_on_shelf,
                    'qty_min': line.qty_min,
                    'qty_in_transit': line.qty_in_transit,
                })
            if not vals:
                raise UserError(_(
                    "Nothing has been shipped to %s yet: there is no table "
                    "to count.", day.fair_id.display_name))
            self.env['event.fair.day.line'].create(vals)
        return True

    def action_close(self):
        for day in self:
            if day.state == 'closed':
                raise UserError(_("Day %s is already closed.", day.date))
            if not day.line_ids:
                raise UserError(_(
                    "Count the table before closing %s.", day.date))
            negative = day.line_ids.filtered(lambda l: l.qty_sold < 0)
            if negative:
                # Contagem MAIOR que o esperado não é venda negativa: ou a
                # reposição não foi lançada, ou a contagem errou. Fechar assim
                # inventaria estoque que não saiu do armazém.
                raise UserError(_(
                    "Counted more than the table should hold: %s. Either a "
                    "replenishment was not recorded, or the count is wrong.",
                    ', '.join(negative.mapped('product_id.display_name'))))
            sold = {
                line.product_id: line.qty_sold
                for line in day.line_ids if line.qty_sold > 0
            }
            if sold:
                picking = day.fair_id._create_fair_picking(
                    'sale', sold,
                    scheduled_date=fields.Datetime.to_datetime(day.date))
                picking.action_assign()
                for move in picking.move_ids:
                    move.quantity = move.product_uom_qty
                    move.picked = True
                picking.button_validate()
                day.picking_id = picking.id
            # A reposição sai ANTES de fechar, e não depois: fechar o dia
            # passa a querer dizer fechado mesmo, sem meia porta aberta.
            # Quem conta a mesa preenche a coluna e fecha uma vez só.
            if any(l.qty_replenish > 0 for l in day.line_ids):
                day.action_replenish()
            day.state = 'closed'
        return True

    def action_replenish(self):
        """A reposição do dia seguinte, decidida onde ela se descobre.

        O lugar certo de pedir reposição é AQUI, e não na aba da grade: é a
        contagem do fim do dia que mostra o que acabou. Pedir na grade obriga
        quem está no balcão a lembrar de cabeça o que faltou e a procurar
        cada título outra vez, numa lista de dezenas.

        Mecanicamente é o mesmo caminho de sempre -- sobe o planejado da
        linha e despacha a diferença --, e por isso a reposição continua
        sendo um segundo movimento contra a MESMA localização, e não um
        remendo. A coluna zera depois de despachar: ela é o pedido de agora,
        não um histórico (o histórico são as transferências).
        """
        pickings = self.env['stock.picking']
        for day in self:
            if day.is_sealed:
                raise UserError(_(
                    "Fair %s has already come back: there is no table left "
                    "to send books to.", day.fair_id.display_name))
            if day.state == 'closed':
                # Dia fechado é dia fechado. Precisando de mais livro depois
                # disso, o pedido é da FEIRA (sobe a grade e despacha), e não
                # de um dia que já foi contado e encerrado -- senão o número
                # do dia deixa de ser o retrato daquele dia.
                raise UserError(_(
                    "Day %s is closed. To send more books now, raise the "
                    "grid on the fair and dispatch from there.", day.date))
            pedido = {
                line.product_id: line.qty_replenish
                for line in day.line_ids if line.qty_replenish > 0
            }
            if not pedido:
                raise UserError(_(
                    "Nothing to replenish: fill the \"To replenish\" column "
                    "with what has to go back to the table."))
            fair = day.fair_id
            por_produto = {
                line.product_id: line for line in fair.line_ids
            }
            # O QUE JÁ ESTÁ A CAMINHO NÃO SE PEDE DE NOVO.
            #
            # A coluna sugerida já desconta o trânsito, mas ela é uma FOTO do
            # dia em que a contagem foi tirada -- e o número é editável. Dois
            # dias diferentes pedindo o mesmo título, ou um pedido digitado
            # por cima de outro que saiu ontem, faziam a mesa receber em
            # dobro justamente o que estava faltando. Foi o que aconteceu com
            # Os Sertões em 11/09/2026: quatro pedidos no fechamento de 30/09
            # e mais quatro no de 29/09, um minuto depois.
            #
            # Aqui a conferência é AO VIVO, na hora de despachar, contra o que
            # a grade sabe: pedido e ainda não chegou, esteja ele parado no
            # armazém ou na estrada.
            ja_a_caminho = {}
            for product in list(pedido):
                linha = por_produto.get(product)
                pendente = linha.qty_requested if linha else 0.0
                if pendente <= 0:
                    continue
                sobra = pedido[product] - pendente
                ja_a_caminho[product] = min(pendente, pedido[product])
                if sobra > 0:
                    pedido[product] = sobra
                else:
                    del pedido[product]
            if not pedido:
                raise UserError(_(
                    "Nothing to send: %(titulos)s already asked for and on "
                    "the way. Wait for it to arrive, or raise the grid on "
                    "the fair if the fair really needs more.",
                    titulos=', '.join(
                        '%s (%s)' % (produto.display_name, int(qtd))
                        for produto, qtd in ja_a_caminho.items())))
            for product, qty in pedido.items():
                linha = por_produto.get(product)
                if linha:
                    linha.qty_planned += qty
                else:
                    self.env['event.fair.line'].create({
                        'fair_id': fair.id,
                        'product_id': product.id,
                        'qty_planned': qty,
                    })
            novos = fair.action_ship()
            # A logística lê a LISTA de transferências, não a ficha de cada
            # uma. Sem dizer no documento de origem que aquilo é reposição de
            # uma feira que já está rolando, a caixa entra na fila como
            # qualquer remessa -- e reposição que chega depois da feira
            # acabar não serve para nada.
            novos.write({
                'fair_day_id': day.id,
                'origin': _('%(feira)s / replenishment of %(dia)s',
                            feira=fair.code, dia=day.date),
            })
            day.replenish_picking_ids = [(4, p.id) for p in novos]
            day.line_ids.write({'qty_replenish': 0.0})
            day._avisar_a_reposicao(pedido, novos, ja_a_caminho)
            pickings |= novos
        return pickings

    def _avisar_a_reposicao(self, pedido, pickings, ja_a_caminho=None):
        """Conta no histórico da feira que a reposição foi pedida.

        Sem isto, a reposição vira movimento e mais nada: quem está no
        armazém recebe uma transferência sem saber que ela é urgente e por
        quê, e quem está na praça não tem como saber se o pedido foi visto. O
        histórico da feira é onde as pessoas do evento já se falam, e quem
        segue a feira recebe o aviso pelo caminho normal.

        A mensagem diz o que se pediu, quanto e por qual transferência --
        para que a conversa que vem depois ("mandaram?", "chegou?") tenha um
        número para citar.
        """
        self.ensure_one()
        if not self.fair_id:
            return False
        linhas = ''.join(
            '<li>%s: <b>%s</b></li>' % (produto.display_name, int(qty))
            for produto, qty in pedido.items())
        refs = ', '.join(pickings.mapped('name'))
        corpo = _(
            "<p><b>%(feira)s</b> — replenishment asked from the closing of "
            "<b>%(dia)s</b>, on <b>%(mov)s</b>:</p><ul>%(linhas)s</ul>",
            feira=self.fair_id.display_name,
            dia=self.date, mov=refs, linhas=linhas)
        # O que foi descontado fica DITO. Quem pediu dez e viu sair quatro
        # precisa saber que os outros seis já estavam na estrada, senão pede
        # de novo amanhã.
        if ja_a_caminho:
            corpo += _(
                "<p>Already on the way, and not asked again: %(titulos)s.</p>",
                titulos=', '.join(
                    '%s (%s)' % (produto.display_name, int(qtd))
                    for produto, qtd in ja_a_caminho.items()))
        self.fair_id.message_post(body=Markup(corpo))
        return True

    def action_view_in_transit(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('On the way'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.in_transit_picking_ids.ids)],
        }


class EventFairDayLine(models.Model):
    _name = 'event.fair.day.line'
    _description = 'Fair Daily Count Line'
    _order = 'day_id, id'

    day_id = fields.Many2one(
        'event.fair.day', string='Day', required=True, ondelete='cascade',
        index=True)
    product_id = fields.Many2one(
        'product.product', string='Title', required=True)
    qty_expected = fields.Float(
        string='Expected', digits='Product Unit', readonly=True,
        help="What the system says should be on the table: opening balance "
             "plus anything replenished today.")
    qty_counted = fields.Float(
        string='Counted', digits='Product Unit',
        help="What is actually on the table at closing time.")
    qty_sold = fields.Float(
        string='Sold', digits='Product Unit', compute='_compute_qty_sold',
        store=True)
    # Carimbado na hora de trazer a mesa, e não lido ao vivo da grade: o
    # fechamento de terça não pode mudar porque alguém mexeu no mínimo na
    # quinta. O que ficou registrado é o que valia naquele dia.
    qty_min = fields.Float(
        string='Minimum', digits='Product Unit', readonly=True,
        help="The minimum the grid asked for this title on the day this "
             "count was taken.")
    # A reposição pedida e ainda não recebida. A equipe não pede reposição
    # todo dia -- é raro --, e por isso um pedido costuma atravessar dias:
    # sai numa noite e chega dois dias depois. Sem descontá-lo, a contagem
    # seguinte sugeriria pedir tudo de novo, e a feira receberia em dobro
    # justamente o título que estava faltando.
    qty_in_transit = fields.Float(
        string='On the way', digits='Product Unit', readonly=True,
        help="Already dispatched to the fair and not received yet, on the "
             "day this count was taken.")
    # Sugerido, não imposto: o número aparece sozinho a partir do mínimo e da
    # contagem, e some por cima dele quem está na praça e sabe que amanhã
    # chove, que a escola não vem, que sobrou espaço na van.
    qty_replenish = fields.Float(
        string='To replenish', digits='Product Unit',
        compute='_compute_qty_replenish', store=True, readonly=False,
        help="How many more copies to send for the next day. Suggested from "
             "the minimum on the table, minus what was counted, minus what "
             "is already on the way; type over it whenever the fair says "
             "otherwise.")

    @api.depends('qty_min', 'qty_counted', 'qty_in_transit')
    def _compute_qty_replenish(self):
        for line in self:
            line.qty_replenish = max(
                0.0, line.qty_min - line.qty_counted - line.qty_in_transit)

    @api.depends('qty_expected', 'qty_counted')
    def _compute_qty_sold(self):
        for line in self:
            line.qty_sold = line.qty_expected - line.qty_counted
