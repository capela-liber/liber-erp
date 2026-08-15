# -*- coding: utf-8 -*-
"""
O espelho do pedido da Amazon, e a cotação que nasce dele.

Por que um modelo próprio em vez de importar direto para `sale.order`:

1. **O pedido muda depois de criado.** Nesta conta, 100% dos pedidos chegam
   já `Acknowledged` ou `Closed` -- alguém confirma no portal da Amazon, na
   mão, e o Vendor Central é hoje o sistema de registro do estado. Reler é
   obrigatório, e reler não pode reescrever por cima de um documento que uma
   pessoa já editou.
2. **Nem todo pedido vira cotação.** Título com ISBN fora do cadastro não tem
   produto para virar linha. O espelho guarda o pedido inteiro de qualquer
   forma, e o problema aparece como relatório em vez de exceção no cron.
3. **A cotação é uma decisão.** Importar é automático; criar documento
   comercial é ato de alguém. É a fronteira que o módulo promete não cruzar.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..services import mapping


class LiberAmazonOrder(models.Model):
    _name = 'liber.amazon.order'
    _description = 'Amazon Vendor Purchase Order'
    _inherit = ['mail.thread']
    _order = 'order_date desc, name desc'

    name = fields.Char(
        string='PO Number', required=True, index=True, readonly=True)
    account_id = fields.Many2one(
        'liber.amazon.account', required=True, readonly=True,
        ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='account_id.company_id', store=True, index=True)

    # O estado como a Amazon o chama, em texto cru. Não é Selection de
    # propósito: o dia em que a Amazon inventar um quarto estado, um Selection
    # recusaria a gravação e perderia o pedido. `state_known` marca o
    # desconhecido sem impedir nada.
    amazon_state = fields.Char(readonly=True, tracking=True)
    amazon_state_label = fields.Char(
        string='Amazon State', compute='_compute_amazon_state_label',
        help="Amazon's own state, in your language. The raw value is kept "
             "underneath: a state Amazon invents tomorrow shows through as "
             "it came, instead of breaking the import.")
    state_known = fields.Boolean(readonly=True)
    is_open = fields.Boolean(
        string='Still Open', readonly=True,
        help="False once Amazon closed the order -- delivered or cancelled.")

    state = fields.Selection(
        [('imported', 'Imported'), ('quoted', 'Quotation created')],
        compute='_compute_state', store=True, default='imported')

    order_date = fields.Datetime(readonly=True, index=True)
    state_changed_date = fields.Datetime(readonly=True)
    delivery_start = fields.Datetime(readonly=True)
    delivery_end = fields.Datetime(readonly=True)

    order_type = fields.Char(readonly=True)
    payment_method = fields.Char(readonly=True)
    buying_party = fields.Char(readonly=True)
    selling_party = fields.Char(readonly=True)
    ship_to_party = fields.Char(readonly=True)

    # ------------------------------------------------ quem está comprando
    # A Amazon manda só a sigla do galpão. Quem ela é aqui dentro sai do mapa
    # de unidades -- ver models/amazon_unit.py.

    unit_id = fields.Many2one(
        'liber.amazon.unit', string='Amazon Unit',
        compute='_compute_unit', store=True, readonly=True)
    unit_mapped = fields.Boolean(
        string='Unit Mapped', compute='_compute_unit', store=True,
        help="False when the buying unit's code has no entry in the mapping. "
             "The order is imported anyway; what it cannot do is become a "
             "quotation, because nobody said which customer it belongs to.")
    partner_id = fields.Many2one(
        'res.partner', string='Customer', compute='_compute_unit', store=True,
        help="Resolved from the buying unit. Falls back to the account's "
             "customer only for orders that carry no unit code at all.")

    line_ids = fields.One2many('liber.amazon.order.line', 'order_id')
    sale_order_id = fields.Many2one(
        'sale.order', string='Quotation', readonly=True, copy=False)

    amount_total = fields.Monetary(
        compute='_compute_amounts', store=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        related='company_id.currency_id', store=True)
    line_count = fields.Integer(compute='_compute_amounts', store=True)
    unmatched_count = fields.Integer(
        compute='_compute_amounts', store=True,
        help="Lines whose ISBN has no product in the catalogue.")

    # ---------------------------------------------------------- as datas
    # O que a operação pergunta o dia inteiro não é quanto vendemos: é o que
    # vence quando. Estes três campos existem para essa pergunta.

    lead_time_days = fields.Integer(
        string='Days Granted', compute='_compute_lead_time', store=True,
        help="Days Amazon gave us, from the order to the end of the delivery "
             "window. Fixed at import: it is a fact about the order, not "
             "about today.")
    days_to_deadline = fields.Integer(
        string='Days Left', compute='_compute_deadline',
        help="Days until the delivery deadline. Negative means overdue. "
             "Empty for orders Amazon already closed.")
    is_late = fields.Boolean(
        string='Overdue', compute='_compute_deadline', search='_search_is_late',
        help="Past the delivery deadline and still open at Amazon.")
    days_to_close = fields.Integer(
        string='Days to Close', compute='_compute_days_to_close', store=True,
        help="Days from the order to the moment Amazon closed it. The closest "
             "thing to a delivery time that the Vendor Orders API gives us -- "
             "but Amazon also closes orders it cancelled, so a very short "
             "cycle is more likely a cancellation than a fast delivery. Zero "
             "while the order is still open.")

    last_sync = fields.Datetime(readonly=True)
    divergence_note = fields.Text(
        readonly=True, copy=False,
        help="Filled when Amazon changed an order after we had already made "
             "a quotation from it. Nothing is rewritten automatically -- "
             "someone reads this and decides.")
    has_divergence = fields.Boolean(compute='_compute_has_divergence', store=True)

    _po_account_uniq = models.Constraint(
        'unique(name, account_id)',
        'This purchase order was already imported for this account.')

    @api.depends('amazon_state')
    def _compute_amazon_state_label(self):
        """
        O estado da Amazon, na língua de quem lê.

        NÃO é gravado: tradução gravada congela no idioma de quem salvou, e
        aqui o valor cru já está guardado ao lado, em `amazon_state`. Estado
        que não conhecemos passa adiante como veio -- que é o mesmo princípio
        do resto do módulo: o desconhecido aparece, não some.
        """
        rotulos = {
            'New': _("New"),
            'Acknowledged': _("Acknowledged"),
            'Closed': _("Closed"),
        }
        for record in self:
            record.amazon_state_label = rotulos.get(
                record.amazon_state, record.amazon_state or '')

    @api.depends('buying_party', 'account_id')
    def _compute_unit(self):
        """
        Da sigla ao cliente.

        Depende de `buying_party` e da conta, e NÃO do mapa -- não há como um
        campo calculado depender de "qualquer unidade com esta sigla". Por
        isso o próprio mapa manda recalcular quando muda; ver
        `liber.amazon.unit._recompute_orders`. Sem isso, criar o mapeamento
        hoje não consertaria os pedidos importados ontem.
        """
        Unit = self.env['liber.amazon.unit']
        for record in self:
            unit = Unit._resolve(record.account_id, record.buying_party)
            record.unit_id = unit
            record.unit_mapped = bool(unit) or not record.buying_party
            record.partner_id = (
                unit.partner_id or
                (record.account_id.partner_id if not record.buying_party
                 else False))

    @api.depends('sale_order_id')
    def _compute_state(self):
        for record in self:
            record.state = 'quoted' if record.sale_order_id else 'imported'

    @api.depends('order_date', 'delivery_end')
    def _compute_lead_time(self):
        """
        Quantos dias a Amazon deu. É gravado porque não muda: é um fato sobre
        o pedido, não sobre hoje -- e por isso pode ser agrupado e somado sem
        envelhecer.
        """
        for record in self:
            if record.order_date and record.delivery_end:
                record.lead_time_days = (
                    record.delivery_end.date() - record.order_date.date()).days
            else:
                record.lead_time_days = 0

    @api.depends('amazon_state', 'order_date', 'state_changed_date')
    def _compute_days_to_close(self):
        """
        Do pedido até a Amazon fechá-lo.

        É o mais perto de "tempo de entrega" que a Vendor Orders API oferece:
        ela não nos conta quando recebeu, conta quando encerrou o documento.
        Serve como medida do ciclo, e não como prova de entrega -- pedido
        cancelado também vira `Closed`, e por isso um ciclo de duas horas
        quase certamente é cancelamento, não velocidade.

        Zero enquanto o pedido está aberto: não há ciclo para medir.
        """
        for record in self:
            if (record.amazon_state == 'Closed' and record.order_date
                    and record.state_changed_date):
                record.days_to_close = (
                    record.state_changed_date.date() - record.order_date.date()).days
            else:
                record.days_to_close = 0

    def _compute_deadline(self):
        """
        Quantos dias faltam, e se já passou.

        NÃO é gravado de propósito: o valor muda sozinho à meia-noite. Campo
        armazenado aqui ficaria velho em silêncio -- o pedido apareceria como
        "faltam 2 dias" uma semana depois de vencer, que é pior do que não ter
        o campo.
        """
        hoje = fields.Date.context_today(self)
        for record in self:
            if not record.delivery_end or not record.is_open:
                record.days_to_deadline = 0
                record.is_late = False
                continue
            faltam = (record.delivery_end.date() - hoje).days
            record.days_to_deadline = faltam
            record.is_late = faltam < 0

    def _search_is_late(self, operator, value):
        """
        Permite filtrar por atraso mesmo o campo não sendo gravado.

        Traduz para uma condição sobre `delivery_end`, que é coluna de
        verdade e tem índice -- o banco resolve, em vez de o Odoo carregar
        todos os pedidos para descobrir quais estão atrasados.
        """
        if operator not in ('=', '!='):
            raise NotImplementedError(
                _("Overdue can only be filtered as yes or no."))
        atrasado = [('delivery_end', '<', fields.Datetime.now()),
                    ('is_open', '=', True)]
        em_dia = ['|', ('delivery_end', '>=', fields.Datetime.now()),
                  ('is_open', '=', False)]
        procura_atrasado = bool(value) if operator == '=' else not value
        return atrasado if procura_atrasado else em_dia

    @api.depends('divergence_note')
    def _compute_has_divergence(self):
        for record in self:
            record.has_divergence = bool(record.divergence_note)

    @api.depends('line_ids.quantity', 'line_ids.price_unit', 'line_ids.product_id')
    def _compute_amounts(self):
        for record in self:
            lines = record.line_ids
            record.line_count = len(lines)
            record.amount_total = sum(
                (line.price_unit or 0.0) * (line.quantity or 0.0)
                for line in lines)
            record.unmatched_count = sum(1 for line in lines if not line.product_id)

    # ------------------------------------------------------- product lookup

    @api.model
    def _match_products(self, isbns):
        """
        Resolve ISBN -> product.product pelo barcode, tolerando hífen.

        A normalização precisa acontecer nos DOIS lados. Há barcode gravado
        com hífen no banco, e a comparação crua faria o título cadastrado
        passar por ausente -- que é o pior erro possível aqui, porque produz
        um relatório mandando cadastrar o que já existe.

        Vai ao SQL porque `replace()` não se escreve em domínio de ORM. Os ids
        que voltam passam pelo `search` antes de serem usados, para que as
        regras de registro e a empresa continuem valendo: SQL cru enxerga o
        banco inteiro, e não é isso que queremos entregar a quem importa.
        """
        wanted = sorted({mapping.normalize_isbn(i) for i in isbns if i})
        if not wanted:
            return {}

        self.env.cr.execute("""
            SELECT id, replace(replace(barcode, '-', ''), ' ', '') AS norm
              FROM product_product
             WHERE barcode IS NOT NULL AND barcode <> ''
               AND replace(replace(barcode, '-', ''), ' ', '') = ANY(%s)
        """, (wanted,))
        rows = self.env.cr.fetchall()
        if not rows:
            return {}

        allowed = set(self.env['product.product'].search(
            [('id', 'in', [row[0] for row in rows])]).ids)

        found = {}
        for product_id, norm in rows:
            if product_id in allowed and norm not in found:
                found[norm] = product_id
        return found

    # ------------------------------------------------------------- sincronia

    @api.model
    def _sync_from_amazon(self, account, raw_orders):
        """
        Grava o espelho. Cria o que é novo, atualiza o que mudou, e não toca
        em documento comercial nenhum.

        Idempotente por construção: a chave é (PO number, conta), e reimportar
        a mesma janela duas vezes não duplica nada -- o que importa, porque a
        janela de leitura recua de propósito e a sobreposição é a regra, não a
        exceção.
        """
        report = mapping.import_report(raw_orders)
        products = self._match_products(
            [line['isbn'] for order in report['mapped'] for line in order['lines']])

        existing = {
            record.name: record
            for record in self.search([
                ('account_id', '=', account.id),
                ('name', 'in', [o['name'] for o in report['mapped'] if o['name']]),
            ])
        }

        created = updated = 0
        now = fields.Datetime.now()

        for mapped in report['mapped']:
            if not mapped['name']:
                continue

            header = {
                key: mapped[key] for key in (
                    'amazon_state', 'state_known', 'is_open', 'order_date',
                    'state_changed_date', 'order_type', 'payment_method',
                    'buying_party', 'selling_party', 'ship_to_party',
                    'delivery_start', 'delivery_end')
            }
            header['last_sync'] = now

            record = existing.get(mapped['name'])
            if record:
                note = record._divergence_against(mapped)
                if note:
                    header['divergence_note'] = note
                record.write(header)
                record._rebuild_lines(mapped['lines'], products)
                updated += 1
            else:
                header.update({'name': mapped['name'], 'account_id': account.id})
                record = self.create(header)
                record._rebuild_lines(mapped['lines'], products)
                created += 1

        return {'created': created, 'updated': updated, 'report': report}

    def _divergence_against(self, mapped):
        """
        Compara o que chegou com o que já está gravado -- e só reclama se já
        existe cotação.

        Antes da cotação, mudança é só notícia: o espelho se atualiza e
        pronto. Depois da cotação, mudança é problema de alguém, porque existe
        um documento comercial afirmando uma quantidade que a Amazon acaba de
        contradizer. A Amazon aceita pedido parcial com frequência, e a
        quantidade confirmada raramente é a pedida.
        """
        self.ensure_one()
        if not self.sale_order_id:
            return False

        changes = []
        if mapped['amazon_state'] and mapped['amazon_state'] != self.amazon_state:
            changes.append(_("state: %(old)s -> %(new)s",
                             old=self.amazon_state or '?',
                             new=mapped['amazon_state']))

        before = {line.item_sequence: line.quantity for line in self.line_ids}
        after = {line['item_sequence']: line['quantity'] for line in mapped['lines']}
        for sequence in sorted(set(before) | set(after)):
            old = before.get(sequence)
            new = after.get(sequence)
            if old != new:
                changes.append(_(
                    "line %(seq)s quantity: %(old)s -> %(new)s",
                    seq=sequence or '?',
                    old='-' if old is None else old,
                    new='-' if new is None else new))

        if not changes:
            return False

        # Teto na lista. Um pedido de 158 linhas que a Amazon reduz produz 158
        # avisos, e o alerta vira um paredão que ninguém lê -- deixando de
        # avisar justamente quando havia mais o que dizer. O número inteiro
        # fica na primeira frase; o detalhe, nas primeiras vinte.
        MOSTRAR = 20
        resto = len(changes) - MOSTRAR
        detalhe = changes[:MOSTRAR]
        if resto > 0:
            detalhe.append(_("… and %s more change(s).", resto))

        return _("Amazon changed this order after quotation %(quote)s was "
                 "created (%(total)s change(s)):\n- %(changes)s",
                 quote=self.sale_order_id.name, total=len(changes),
                 changes="\n- ".join(detalhe))

    def _rebuild_lines(self, mapped_lines, products):
        """
        Refaz as linhas do espelho a partir do que a Amazon mandou agora.

        Produto escolhido à mão sobrevive: se alguém corrigiu o casamento de
        uma linha -- porque o ISBN mudou de edição, porque o cadastro tem dois
        registros -- essa decisão não pode ser desfeita pela próxima leitura.
        """
        self.ensure_one()
        locked = {
            line.item_sequence: line.product_id.id
            for line in self.line_ids if line.product_locked and line.product_id
        }
        self.line_ids.unlink()

        values = []
        for line in mapped_lines:
            product_id = locked.get(line['item_sequence']) or products.get(
                line['isbn'] or '')
            values.append({
                'order_id': self.id,
                'item_sequence': line['item_sequence'],
                'isbn': line['isbn'],
                'asin': line['asin'],
                'quantity': line['quantity'],
                'uom_label': line['uom'],
                'price_unit': line['price_unit'] or 0.0,
                'currency_code': line['currency'],
                'list_price': line['list_price'] or 0.0,
                'backorder_allowed': line['backorder_allowed'],
                'product_id': product_id,
                'product_locked': line['item_sequence'] in locked,
            })
        if values:
            self.env['liber.amazon.order.line'].with_context(
                amazon_sync=True).create(values)

    # --------------------------------------------------------------- cotação

    def action_create_quotation(self):
        return self._create_quotation()

    def _quotation_blockers(self):
        """
        Tudo o que impede este pedido de virar cotação, em texto legível.

        Existe em um lugar só porque há dois caminhos até a cotação -- o botão
        do formulário e a ação em massa -- e regra de negócio duplicada
        diverge: um dia o botão recusa o que a lista aceita, e ninguém
        descobre até um pedido sair errado.

        Lista vazia quer dizer pronto.
        """
        self.ensure_one()
        blockers = []

        if self.sale_order_id:
            blockers.append(_(
                "%(po)s already has quotation %(quote)s.",
                po=self.name, quote=self.sale_order_id.name))

        if not self.is_open:
            # A Amazon fechou: entregue, cancelado ou expirado. Cotar agora
            # criaria um compromisso comercial para uma janela que não existe
            # mais -- e, no histórico importado, prometeria de novo o que já
            # foi entregue pelo portal.
            blockers.append(_(
                "Amazon already closed %s. There is no open window to quote "
                "against.", self.name))

        if not self.partner_id:
            if self.buying_party:
                # Cair no cliente da conta seria pior do que recusar: cada
                # unidade da Amazon é um estabelecimento fiscal com CNPJ
                # próprio, e a nota sairia contra o errado -- em silêncio,
                # com número plausível.
                blockers.append(_(
                    "Amazon unit %(code)s is not mapped to a customer. Map it "
                    "under Configuration > Amazon Units, or use 'Map units "
                    "from orders' on the account.",
                    code=self.buying_party))
            else:
                blockers.append(_(
                    "Set 'Amazon as Customer' on account %s before creating "
                    "quotations.", self.account_id.display_name))

        # Linha sem produto NÃO impede a cotação: ela fica de fora e o que
        # ficou de fora é registrado no histórico. Bloquear seria pior --
        # trava o pedido inteiro por um título que talvez nem seja nosso, e a
        # Amazon não espera. O que não pode é sumir em silêncio: a cotação
        # promete menos do que foi pedido, e alguém precisa saber disso.
        usable = self.line_ids.filtered(lambda line: line.product_id)

        if not usable:
            blockers.append(_(
                "%s has no line that can become a quotation.", self.name))

        company_currency = self.company_id.currency_id.name
        foreign = sorted({
            line.currency_code for line in usable
            if line.currency_code and line.currency_code != company_currency})
        if foreign:
            blockers.append(_(
                "%(po)s is priced in %(foreign)s but the company books in "
                "%(company)s. Converting silently would put a plausible wrong "
                "number in the quotation.",
                po=self.name, foreign=", ".join(foreign),
                company=company_currency))

        return blockers

    def action_create_quotations_bulk(self):
        """
        A ação em massa: cotação para tudo o que está pronto, e um relatório
        do que ficou de fora.

        Aqui a regra é o contrário da do botão individual. No formulário,
        falhar é a resposta certa -- a pessoa está olhando aquele pedido e
        quer saber o que há de errado com ele. Numa seleção de cinquenta,
        levantar exceção no terceiro desperdiça o trabalho dos outros
        quarenta e sete e não diz o que aconteceu. Então aqui se pula, se
        conta e se explica.

        O que não muda: nada é confirmado, nem aqui nem na Amazon.
        """
        pronto = self.env['liber.amazon.order']
        pulados = []
        for record in self:
            blockers = record._quotation_blockers()
            if blockers:
                # O primeiro motivo basta: resolvido ele, a pessoa reabre a
                # lista e vê o seguinte, se houver.
                pulados.append((record.name, blockers[0]))
            else:
                pronto |= record

        # Contado ANTES de criar: depois da cotação a informação continua nas
        # linhas, mas o número que interessa é o desta rodada.
        ignoradas = sum(pedido.unmatched_count for pedido in pronto)

        if pronto:
            pronto._create_quotation()

        if not pronto and not pulados:
            mensagem = _("Nothing was selected.")
        elif not pulados:
            mensagem = _("%s quotation(s) created, all in draft. "
                         "Nothing was confirmed.", len(pronto))
        else:
            amostra = "\n".join(
                "• %s — %s" % (name, motivo.split("\n")[0])
                for name, motivo in pulados[:8])
            resto = len(pulados) - 8
            if resto > 0:
                amostra += _("\n… and %s more.", resto)
            mensagem = _(
                "%(feitas)s quotation(s) created, %(pulados)s skipped:\n\n"
                "%(amostra)s",
                feitas=len(pronto), pulados=len(pulados), amostra=amostra)

        if ignoradas:
            mensagem += _(
                "\n\n%s line(s) were left out for having no product in the "
                "catalogue — see each order's log.", ignoradas)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if pronto and not pulados else 'warning',
                'title': _("Quotations"),
                'message': mensagem,
                # Fica na tela: relatório que some antes de ser lido não é
                # relatório.
                'sticky': bool(pulados),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _create_quotation(self):
        """
        Cria a cotação -- e a deixa cotação.

        Nada é confirmado: sem `action_confirm`, sem reserva de estoque, sem
        fatura. Quem confirma é uma pessoa, depois de olhar. Essa é a fronteira
        que o módulo promete não cruzar, e o teste
        `test_quotation_is_never_confirmed` existe para que a promessa não
        dependa de ninguém se lembrar dela.
        """
        quotations = self.env['sale.order']
        for record in self:
            blockers = record._quotation_blockers()
            if blockers:
                # Todos de uma vez: mandar a pessoa consertar um problema para
                # descobrir o seguinte é fazê-la voltar três vezes.
                raise UserError("\n\n".join(blockers))

            usable = record.line_ids.filtered(lambda line: line.product_id)
            entrega = (record.unit_id.shipping_partner_id
                       or record.partner_id)

            quotation = self.env['sale.order'].create({
                'partner_id': record.partner_id.id,
                'partner_shipping_id': entrega.id,
                'company_id': record.company_id.id,
                'origin': record.name,
                'client_order_ref': record.name,
                'date_order': record.order_date or fields.Datetime.now(),
                # A janela de entrega da Amazon é um intervalo; o fim é o
                # prazo. Prometer o começo seria prometer mais do que ela pede.
                'commitment_date': record.delivery_end or False,
                # Sem price_unit de propósito (decisão de 11/08/2026): a
                # cotação nasce com o NOSSO preço de capa, calculado pelo
                # padrão do Odoo (lista de preços do parceiro, desconto e
                # tudo). O valor da Amazon (Net Cost) não se perde: fica no
                # espelho da PO, que é onde comparação e divergência moram.
                'order_line': [
                    (0, 0, {
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.quantity,
                        'name': line.product_id.display_name,
                    })
                    for line in usable
                ],
            })
            record.sale_order_id = quotation

            # O que ficou de fora fica escrito. Ignorar a linha sem produto é
            # a decisão certa -- ela não trava o pedido --, mas ignorar em
            # silêncio não é: a cotação promete menos exemplares do que a
            # Amazon pediu, e a diferença só apareceria na entrega.
            ignoradas = record.line_ids - usable
            if ignoradas:
                record.message_post(body=_(
                    "Quotation %(name)s created from this purchase order. "
                    "It was NOT confirmed, and nothing was sent to Amazon."
                    "\n\n%(count)s line(s) were left out for having no "
                    "product in the catalogue:\n%(isbns)s",
                    name=quotation.name, count=len(ignoradas),
                    isbns="\n".join(sorted(
                        line.isbn or _("(line %s, no ISBN)", line.item_sequence)
                        for line in ignoradas))))
            else:
                record.message_post(body=_(
                    "Quotation %(name)s created from this purchase order. "
                    "It was NOT confirmed, and nothing was sent to Amazon.",
                    name=quotation.name))
            quotations |= quotation

        return quotations._get_records_action(name=_("Quotations")) \
            if hasattr(quotations, '_get_records_action') else {
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'view_mode': 'list,form',
                'domain': [('id', 'in', quotations.ids)],
            }

    def action_view_quotation(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
        }

    def action_clear_divergence(self):
        """Alguém leu e resolveu. O aviso sai, o histórico fica no chatter."""
        for record in self:
            if record.divergence_note:
                record.message_post(body=_(
                    "Divergence acknowledged:\n%s", record.divergence_note))
        self.divergence_note = False


class LiberAmazonOrderLine(models.Model):
    _name = 'liber.amazon.order.line'
    _description = 'Amazon Vendor Purchase Order Line'
    _order = 'order_id, item_sequence'

    order_id = fields.Many2one(
        'liber.amazon.order', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True)

    item_sequence = fields.Char(readonly=True)
    isbn = fields.Char(string='ISBN', readonly=True, index=True)
    asin = fields.Char(string='ASIN', readonly=True)

    product_id = fields.Many2one(
        'product.product',
        help="Resolved from the ISBN against the product barcode. Set it by "
             "hand when the catalogue disagrees -- your choice survives the "
             "next import.")
    product_locked = fields.Boolean(
        readonly=True,
        help="True once a person chose the product, so re-reading Amazon "
             "does not undo it.")

    short_label = fields.Char(
        string='Title', compute='_compute_short_label', store=True,
        help="ISBN plus the first words of the title. Exists because the "
             "pivot has no column width: a row header is as wide as its "
             "longest label, and one long title stretches the whole table.")

    quantity = fields.Float(readonly=True)
    uom_label = fields.Char(string='Amazon UoM', readonly=True)
    # netCost, o que a Amazon paga -- nunca listPrice, que é a etiqueta com
    # que ela revende. Trocar os dois infla a receita e só aparece no
    # fechamento do mês.
    price_unit = fields.Float(string='Net Cost', readonly=True, digits='Product Price')
    list_price = fields.Float(readonly=True, digits='Product Price')
    currency_code = fields.Char(readonly=True)
    backorder_allowed = fields.Boolean(readonly=True)

    # Gravado, ao contrário de antes: medida de pivô precisa existir em coluna.
    subtotal = fields.Float(
        compute='_compute_subtotal', store=True, digits='Product Price')
    matched = fields.Boolean(compute='_compute_subtotal', store=True)

    # ------------------------------------------------- o pedido, espelhado
    # A pergunta "quais livros não foram atendidos" é por TÍTULO, e título
    # mora na linha. Para o pivô agrupar por mês, estado ou destino, esses
    # campos do pedido precisam existir aqui -- relacionado sem `store` não
    # entra em agrupamento.

    categ_id = fields.Many2one(
        'product.category', string='Product Category',
        related='product_id.categ_id', store=True,
        help="Category of the matched product. Empty for titles with no "
             "product in the catalogue -- they group under 'None'.")

    order_date = fields.Datetime(
        related='order_id.order_date', store=True, index=True)
    amazon_state = fields.Char(related='order_id.amazon_state', store=True)
    amazon_state_label = fields.Char(
        string='Amazon State', related='order_id.amazon_state_label')
    ship_to_party = fields.Char(
        string='Destination', related='order_id.ship_to_party', store=True)
    days_to_close = fields.Integer(
        related='order_id.days_to_close', store=True)
    lead_time_days = fields.Integer(
        related='order_id.lead_time_days', store=True)

    fulfilment_state = fields.Selection(
        [('no_product', 'No product in catalogue'),
         ('pending', 'Not quoted yet'),
         ('quoted', 'In a quotation')],
        string='Fulfilment', compute='_compute_fulfilment', store=True,
        help="Where this title stopped. 'No product in catalogue' means it "
             "was left out of the quotation for having no product; 'Not "
             "quoted yet' means nobody turned the order into a quotation.")

    # `fulfilment_state` diz ONDE parou; este diz SE ainda dá para andar. São
    # eixos diferentes, e juntá-los num campo só faria perder um dos dois: um
    # título sem cadastro num pedido aberto ainda é recuperável, e o mesmo
    # título num pedido que a Amazon fechou não é.
    outcome = fields.Selection(
        [('served', 'Quoted here'),
         ('open', 'Still possible'),
         ('missed', 'Window closed')],
        string='Status in Odoo', compute='_compute_fulfilment', store=True,
        help="Where this title stands INSIDE ODOO -- not what happened in the "
             "world.\n\n"
             "'Quoted here' counts only what became a quotation through this "
             "module. A year of history was imported after the fact, so almost "
             "nothing old can be quoted here: those books were delivered "
             "through the Vendor Central portal, before this module existed.\n\n"
             "'Window closed' means Amazon closed the order without this title "
             "reaching a quotation. For the imported history that is the "
             "normal case and not a loss; for orders that arrive from now on, "
             "it is a miss worth looking at.")

    # Comprimento do pedaço do título. 34 cabe numa coluna que não empurra o
    # resto da tabela para fora da tela, e ainda deixa reconhecer o livro.
    SHORT_TITLE = 34

    @api.depends('isbn', 'product_id.name')
    def _compute_short_label(self):
        """
        ISBN na frente, título cortado atrás.

        O ISBN não está aí por capricho de catálogo: dois títulos de uma mesma
        coleção costumam começar igual, e cortados no mesmo ponto virariam o
        MESMO rótulo -- o pivô somaria os dois numa linha só e o número sairia
        errado sem nada na tela denunciando. Com o ISBN na frente, cada linha
        é única mesmo quando o texto colide.
        """
        for line in self:
            nome = line.product_id.name or _("(not in catalogue)")
            if len(nome) > line.SHORT_TITLE:
                nome = nome[:line.SHORT_TITLE - 1].rstrip() + '…'
            line.short_label = '%s · %s' % (line.isbn or '—', nome)

    @api.depends('quantity', 'price_unit', 'product_id')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = (line.quantity or 0.0) * (line.price_unit or 0.0)
            line.matched = bool(line.product_id)

    @api.depends('product_id', 'order_id.sale_order_id', 'order_id.is_open')
    def _compute_fulfilment(self):
        """
        Onde este título parou, e se ainda dá para fazer algo.

        Duas perguntas, dois campos. A primeira é de causa -- e separar 'sem
        produto' de 'sem cotação' importa porque são problemas de gente
        diferente: um é do cadastro, o outro de quem opera. A segunda é de
        prazo: enquanto o pedido está aberto na Amazon, cadastrar o título
        ainda resolve; depois que ela fecha, aquele título naquele pedido não
        vai mais a lugar nenhum.
        """
        for line in self:
            if not line.product_id:
                line.fulfilment_state = 'no_product'
            elif not line.order_id.sale_order_id:
                line.fulfilment_state = 'pending'
            else:
                line.fulfilment_state = 'quoted'

            if line.fulfilment_state == 'quoted':
                line.outcome = 'served'
            elif line.order_id.is_open:
                line.outcome = 'open'
            else:
                line.outcome = 'missed' 

    def write(self, vals):
        """
        Produto escolhido por gente fica trancado.

        A sincronia escreve com `amazon_sync` no contexto; qualquer outra
        escrita de `product_id` é decisão humana e passa a sobreviver às
        próximas leituras.
        """
        if 'product_id' in vals and not self.env.context.get('amazon_sync'):
            vals = dict(vals, product_locked=bool(vals.get('product_id')))
        return super().write(vals)
