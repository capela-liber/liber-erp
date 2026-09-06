# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """Consignment Pedido = a sale.order flagged is_consignment.

    Same model and same flow as a real sale (the team already knows it), but it
    is NOT a sale: it gets the "C" code instead of "S", is kept out of the Sales
    app / Sales Analysis by domains, and only becomes revenue at the Acerto.
    """
    _inherit = 'sale.order'

    is_consignment = fields.Boolean(
        string='Consignment Order', default=False, copy=False, index=True,
        help="Consignment order (Pedido C). Follows the sale flow but is not a "
             "sale: excluded from Sales reporting; revenue only at the Acerto.")
    consignment_type = fields.Selection([
        ('opening', 'Consignment Opening'),
        ('replenishment', 'Replenishment'),
    ], string='Consignment Type', copy=False,
        help="Opening = first placement of stock, created directly (no map "
             "needed). Replenishment = a refill fired by a consignment operation "
             "(CO) after the map. A Pedido created by hand can only be an opening.")
    consignment_agreement_id = fields.Many2one(
        'consignment.agreement', string='Consignment Agreement',
        compute='_compute_consignment_agreement_id', store=True, readonly=True,
        help="Resolved from the customer (one agreement per customer).")

    @api.depends('partner_id', 'company_id', 'is_consignment')
    def _compute_consignment_agreement_id(self):
        Agreement = self.env['consignment.agreement']
        for order in self:
            if order.is_consignment and order.partner_id:
                order.consignment_agreement_id = Agreement._resolve_for(
                    order.partner_id.commercial_partner_id, order.company_id)
            else:
                order.consignment_agreement_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_consignment') and vals.get('name', _('New')) in (
                    False, '/', _('New')):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sale.order.consignment') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Um S nao vira C depois de nascido
    # ------------------------------------------------------------------
    # Em agosto/2026 apareceram 21 pedidos com nome de VENDA (S63072,
    # S63495...) e `is_consignment` ligado. Eles somem da lista de Pedidos,
    # somem da Analise de vendas, nao faturam -- e continuam se chamando S.
    # O comercial procura o pedido pelo numero, nao acha, e a nota ja saiu
    # como remessa (5917).
    #
    # Nao foi possivel reconstituir o clique: `cfop_id` nao esta em view
    # nenhuma de sale.order no prod, nenhum dos 21 veio do acerto
    # (`consignment_operation_id` vazio) e os campos nao sao rastreados. Por
    # isso a trava fica AQUI, no write, onde toda porta precisa passar --
    # tela, importacao, RPC ou codigo nosso.
    #
    # A regra e simples: a bandeira se decide no nascimento. Depois de
    # confirmado, ninguem mais a muda. Em rascunho pode mudar, mas ai o NOME
    # muda junto: nome e bandeira nunca mais discordam.
    def write(self, vals):
        if 'is_consignment' in vals:
            alvo = bool(vals['is_consignment'])
            mudando = self.filtered(lambda o: o.is_consignment != alvo)
            firmes = mudando.filtered(lambda o: o.state not in ('draft', 'sent'))
            if firmes:
                raise UserError(_(
                    "%(orders)s: a consignment order and a sale are different "
                    "documents, and this one is already confirmed. Cancel it and "
                    "create the right document instead of converting it.",
                    orders=', '.join(firmes.mapped('name'))))
            if mudando and 'name' not in vals:
                # O NOME TEM DE VIAJAR NO MESMO WRITE. A constrains abaixo
                # roda no flush, dentro do super() -- renumerar depois chega
                # tarde: o pedido ja passou pela rede com nome de venda e a
                # propria trava recusa a troca legitima.
                codigo = ('sale.order.consignment' if alvo else 'sale.order')
                Sequencia = self.env['ir.sequence']
                for order in mudando:
                    proximo = Sequencia.next_by_code(codigo)
                    super(SaleOrder, order).write(
                        dict(vals, name=proximo) if proximo else vals)
                intactos = self - mudando
                if intactos:
                    super(SaleOrder, intactos).write(vals)
                return True
        return super().write(vals)

    @api.constrains('name', 'is_consignment')
    def _check_nome_combina_com_bandeira(self):
        """Rede de baixo: consignacao com nome de venda nao existe.

        Le o prefixo da sequencia de venda em vez de cravar "S" no codigo --
        a casa ja renumerou series antes e vai renumerar de novo."""
        sequencia = self.env['ir.sequence'].search(
            [('code', '=', 'sale.order')], limit=1)
        prefixo = (sequencia.prefix or '').strip()
        if not prefixo:
            return
        for order in self:
            if order.is_consignment and (order.name or '').startswith(prefixo):
                raise UserError(_(
                    "%(order)s is flagged as a consignment order but carries a "
                    "sale number. A consignment order is not a sale: it has to "
                    "carry its own number.", order=order.name))

    # ------------------------------------------------------------------
    # Sem contrato ativo não sai livro
    # ------------------------------------------------------------------
    # A CONSIGNAÇÃO COMEÇA NO CONTRATO, e o Pedido era a única porta sem
    # porteiro (24/08/2026). A Movimentação (CR/CO) já recusava desde sempre:
    # `consignment.move.action_confirm` exige contrato, e exige que ele esteja
    # ativo. O Pedido C confirmava para qualquer um.
    #
    # O que isso produzia não era um aviso perdido: era livro sem lugar para
    # ir. O destino da remessa é a prateleira do contrato (ver stock_rule.py);
    # sem contrato não há prateleira, e a remessa caía de volta em "Clientes" --
    # o livro saía do estoque e não entrava em prateleira nenhuma. Dois pedidos
    # do prod tinham nascido assim quando a equipe percebeu.
    #
    # Suspenso barra pelo mesmo motivo, e é o motivo de suspender existir: quem
    # suspende quer parar de mandar livro. Um Pedido C que passa por cima faz
    # da suspensão um enfeite.
    #
    # A trava é no CONFIRMAR, não no criar: o comercial monta o pedido, vê o
    # que está montando, e é na hora de mandar para o depósito que a casa
    # cobra o contrato. O contrato fechado cai na mesma mensagem do suspenso --
    # `_resolve_for` o encontra, e o estado dele explica por que não serve.
    def _check_consignment_agreement(self):
        self.ensure_one()
        agreement = self.consignment_agreement_id
        if not agreement:
            raise UserError(_(
                "%(customer)s has no consignment agreement: %(order)s cannot "
                "be confirmed.\n\n"
                "A consignment order ships to the customer's shelf, and the "
                "shelf is born with the agreement. Open the agreement (AC) for "
                "this customer and activate it first.",
                customer=self.partner_id.display_name, order=self.name))
        if agreement.state != 'active':
            raise UserError(_(
                "The consignment agreement %(ref)s of %(customer)s is "
                "%(state)s: %(order)s cannot be confirmed.\n\n"
                "Only an active agreement receives goods. Reactivate it, or "
                "settle what is on the shelf before sending more.",
                ref=agreement.name, customer=self.partner_id.display_name,
                # _description_selection, e não `.selection` cru: é ele que
                # traduz o rótulo. A mensagem diz "está Suspenso" para quem lê
                # em português, e não o valor técnico 'suspended'.
                state=dict(agreement._fields['state']._description_selection(
                    self.env)).get(agreement.state, agreement.state),
                order=self.name))

    def action_confirm(self):
        for order in self.filtered('is_consignment'):
            order._check_consignment_agreement()
        return super().action_confirm()

    # ------------------------------------------------------------------
    # A Pedido C does not invoice
    # ------------------------------------------------------------------
    # Consignment is not a sale: the book on the customer's shelf is still ours, and
    # it becomes revenue at the Acerto -- which issues the fiscal note (CFOP 5113/6113)
    # and the invoice. Invoicing the Pedido would book revenue for goods nobody bought
    # yet, and it would do it twice: once here, once at the settlement.
    def _get_invoiceable_lines(self, final=False):
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(lambda l: not l.order_id.is_consignment)

    def _create_invoices(self, grouped=False, final=False, date=None):
        consignacao = self.filtered('is_consignment')
        if consignacao:
            raise UserError(_(
                "A consignment order does not invoice: %(orders)s.\n\n"
                "The books are still ours, on the customer's shelf. They become "
                "revenue at the Acerto -- which is what issues the note and the "
                "invoice, for what was actually sold.",
                orders=", ".join(consignacao.mapped('name')),
            ))
        return super()._create_invoices(grouped=grouped, final=final, date=date)

    @api.depends('is_consignment')
    def _compute_invoice_status(self):
        super()._compute_invoice_status()
        # Nothing to invoice, ever: the button and the "to invoice" lists leave it alone.
        self.filtered('is_consignment').invoice_status = 'no'
