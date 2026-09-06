# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_is_zero


class ConsignmentAgreement(models.Model):
    _name = 'consignment.agreement'
    _description = 'Consignment Agreement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'), index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, tracking=True,
        domain=[('is_company', '=', True)])
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    user_id = fields.Many2one(
        'res.users', string='Commercial Agent', tracking=True,
        default=lambda self: self.env.user)
    # O CANAL NASCE DO CLIENTE, e não se digita duas vezes.
    #
    # Até 08/08/2026 o default era `_get_default_team_id()`, a heurística do
    # Odoo -- que olha as equipes do VENDEDOR, não o cliente. Ela nunca teve
    # como acertar: numa medição no `merge_02`, 77 dos 262 contratos diziam um
    # canal diferente do da ficha do cliente, e um deles dizia "Sales", a
    # equipe de fábrica. Ninguém tinha decidido nada disso; era o chute.
    #
    # `store` + `readonly=False` é herança COM exceção, e funciona como a lista
    # de preço do pedido: trocou o cliente, o canal acompanha; depois disso,
    # quem quiser muda à mão e o valor fica.
    #
    # O que NÃO reescreve o valor é corrigir a ficha do cliente depois: a
    # dependência é `partner_id` (o vínculo), não `partner_id.team_id`. Por isso
    # um contrato de 2024 continua no canal em que foi feito mesmo que a ficha
    # seja reclassificada hoje -- e é essa a diferença entre carimbo e espelho.
    team_id = fields.Many2one(
        'crm.team', string='Sales Channel', tracking=True,
        compute='_compute_team_id', store=True, readonly=False, precompute=True)

    @api.depends('partner_id', 'company_id')
    def _compute_team_id(self):
        for acordo in self:
            acordo.team_id = acordo.partner_id._soc_sales_channel(acordo.company_id) \
                if acordo.partner_id else acordo.team_id
    report_contact_ids = fields.Many2many(
        'res.partner', 'consignment_agreement_report_contact_rel',
        'agreement_id', 'partner_id', string='Report Recipients',
        help="One or more commercial contacts of this customer who may receive "
             "the consignment reports (statements, return notices, etc.).")

    location_id = fields.Many2one(
        'stock.location', string='Customer Shelf', copy=False, tracking=True,
        help="Internal location that holds our stock physically placed at this customer. "
             "Created automatically when the agreement is activated.")
    pricelist_id = fields.Many2one(
        'product.pricelist', string='Pricelist',
        help="Commercial condition applied at settlement.")
    discount = fields.Float(
        string='Default Discount %',
        help="Blanket discount granted to this customer. Settlement lines "
             "inherit it (still editable per line).")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', required=True, tracking=True)

    settlement_frequency = fields.Selection([
        ('weekly', 'Weekly'),
        ('biweekly', 'Biweekly'),
        ('monthly', 'Monthly'),
    ], string='Settlement Frequency', default='monthly')
    replenishment_policy = fields.Selection([
        ('manual', 'Manual'),
        ('min_max', 'Min / Max'),
        ('sell_through', 'Sell-through'),
    ], string='Replenishment Policy', default='manual')

    date_start = fields.Date(string='Start Date', default=fields.Date.context_today)
    date_end = fields.Date(string='End Date')
    note = fields.Text(string='Notes')
    active = fields.Boolean(default=True)

    on_shelf_qty = fields.Integer(
        string='On-shelf Qty', compute='_compute_on_shelf',
        help="Units currently on the customer's shelf (still ours).")
    on_shelf_product_count = fields.Integer(
        string='On-shelf Products', compute='_compute_on_shelf')

    @api.depends('location_id')
    def _compute_on_shelf(self):
        Quant = self.env['stock.quant']
        for agr in self:
            qty = 0.0
            products = self.env['product.product']
            if agr.location_id:
                quants = Quant.search([
                    ('location_id', '=', agr.location_id.id),
                    ('quantity', '>', 0),
                ])
                qty = sum(quants.mapped('quantity'))
                products = quants.mapped('product_id')
            agr.on_shelf_qty = int(round(qty))
            agr.on_shelf_product_count = len(products)

    # ------------------------------------------------------------------
    # A casa nao consigna para si mesma
    # ------------------------------------------------------------------
    # Em agosto/2026 abriram-se dois contratos em que o CLIENTE era a propria
    # empresa: o 275 (Edlab Press, 24/08) e o 285 (n-1, 27/08). Cada um ganhou
    # sua prateleira, e um ajuste de auditoria empurrou o estoque da casa para
    # dentro dela: 6.711 e 20.691 exemplares, R$ 2,08 milhoes a preco de capa.
    #
    # O estrago nao e contabil, e operacional: livro em prateleira de
    # consignacao nao esta disponivel para vender. O armazem da n-1 foi a zero
    # nos titulos afetados e cinco pedidos da Amazon ficaram sem atendimento
    # com o livro no predio.
    #
    # Consignacao e um acordo entre DUAS partes: o livro continua nosso, mas
    # esta em poder de outro. Cliente igual a fornecedor nao e acordo nenhum:
    # e o estoque parado no proprio armazem, com outro nome.
    #
    # O recorte e ESTREITO de proposito. Uma empresa do grupo consignar para
    # OUTRA e legitimo e acontece: a Edlab Press pode deixar livro na
    # prateleira da n-1, e ali ha duas partes de verdade, com estoque que
    # muda de maos. O que nao existe e a empresa consignar para ela mesma.
    @api.constrains('partner_id', 'company_id')
    def _check_partner_nao_e_a_propria_empresa(self):
        for agr in self:
            parceiro = agr.partner_id.commercial_partner_id or agr.partner_id
            if agr.company_id and parceiro == agr.company_id.partner_id:
                raise ValidationError(_(
                    "%(partner)s is the company that owns this agreement: "
                    "there is no consignment to open with itself.\n\n"
                    "A consignment agreement puts our books in SOMEONE ELSE'S "
                    "hands. Books consigned to ourselves leave the warehouse "
                    "on paper and stop being available to sell, while sitting "
                    "on the same shelf they always were. Consigning to "
                    "ANOTHER company of the group is fine: there the books "
                    "really do change hands.",
                    partner=agr.partner_id.display_name))

    @api.constrains('partner_id', 'company_id', 'state')
    def _check_single_agreement(self):
        # At most one OPEN contract per customer (per company). A closed contract
        # is history -- it never conflicts, and a new agreement can be created
        # once the previous one is closed.
        for agr in self:
            if agr.state == 'closed':
                continue
            duplicate = self.search([
                ('id', '!=', agr.id),
                ('partner_id', '=', agr.partner_id.id),
                ('company_id', '=', agr.company_id.id),
                ('state', '!=', 'closed'),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    "%(partner)s already has an open consignment agreement "
                    "(%(ref)s). Close it before opening a new one.",
                    ref=duplicate.name, partner=agr.partner_id.display_name))

    @api.model
    def _resolve_for(self, partner, company):
        """The customer's operative agreement: prefer a non-closed one, and fall
        back to any (so a closed consignment's shelf/history still resolves, e.g.
        for the audit). Returns an empty recordset when the customer has none."""
        if not partner:
            return self.browse()
        company_id = company.id if company else self.env.company.id
        base = [('partner_id', '=', partner.id), ('company_id', '=', company_id)]
        return (self.search(base + [('state', '!=', 'closed')], limit=1)
                or self.search(base, limit=1))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'consignment.agreement') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def action_activate(self):
        for agr in self:
            if not agr.location_id:
                agr.location_id = agr._create_shelf_location()
            # sudo pelo mesmo motivo da prateleira: os dois campos são a
            # contabilidade do contrato na ficha do cliente, não cadastro de
            # contato. Quem opera consignação pode não ter direito de GRAVAR
            # em res.partner (o Assistente Comercial não cadastra contato), e
            # sem isto a ativação morreria no passo seguinte ao do local.
            agr.partner_id.sudo().write({
                'consignment_location_id': agr.location_id.id,
                'allow_consignment': True,
            })
            agr.state = 'active'

    def action_suspend(self):
        self.write({'state': 'suspended'})

    def action_reactivate(self):
        self.write({'state': 'active'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_close(self):
        for agr in self:
            if not float_is_zero(agr.on_shelf_qty, precision_rounding=0.001):
                raise UserError(_(
                    "Cannot close agreement %(ref)s: the shelf still holds %(qty).2f units. "
                    "Settle or recall the remaining stock first.",
                    ref=agr.name, qty=agr.on_shelf_qty))
            agr.state = 'closed'

    # ------------------------------------------------------------------
    # Shelf location
    # ------------------------------------------------------------------
    def _create_shelf_location(self):
        self.ensure_one()
        parent = self._get_consignment_root_location()
        # sudo DELIBERADO, pelo mesmo motivo da raiz CO (ver
        # stock_location._soc_consignment_root): a prateleira é consequência de
        # ativar o contrato, não uma localização que o Comercial abriu à mão.
        # O que ele pode criar aqui é exatamente uma prateleira, deste parceiro,
        # sob a raiz da empresa dele -- os valores são todos daqui, nenhum vem
        # da tela. Ativar o contrato é o direito; o local é o efeito.
        return self.env['stock.location'].sudo().create({
            'name': self.partner_id.name,
            'usage': 'internal',
            'location_id': parent.id,
            'company_id': self.company_id.id,
            'is_consignment_shelf': True,
            'consignment_partner_id': self.partner_id.id,
        }).sudo(False)

    def _get_consignment_root_location(self):
        self.ensure_one()
        return self.env['stock.location']._soc_consignment_root(self.company_id)

    def action_view_shelf(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shelf Stock'),
            'res_model': 'stock.quant',
            'view_mode': 'list,form',
            'domain': [('location_id', '=', self.location_id.id)],
            'context': {'search_default_productgroup': 1},
        }
