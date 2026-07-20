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
    team_id = fields.Many2one(
        'crm.team', string='Sales Team', tracking=True,
        default=lambda self: self.env['crm.team']._get_default_team_id())
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
            agr.partner_id.consignment_location_id = agr.location_id
            agr.partner_id.allow_consignment = True
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
        return self.env['stock.location'].create({
            'name': self.partner_id.name,
            'usage': 'internal',
            'location_id': parent.id,
            'company_id': self.company_id.id,
            'is_consignment_shelf': True,
            'consignment_partner_id': self.partner_id.id,
        })

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
