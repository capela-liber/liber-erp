# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConsignmentMove(models.Model):
    _name = 'consignment.move'
    _description = 'Consignment Returns'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    # Clicking this model in the Activities systray opens the activity view
    # (only records with a scheduled task), not the full list of movements.
    _systray_view = 'activity'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'), index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True, tracking=True,
        domain=[('allow_consignment', '=', True)])
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    agreement_id = fields.Many2one(
        'consignment.agreement', string='Agreement',
        compute='_compute_agreement_id', store=True, readonly=True,
        help="Resolved from the customer (one agreement per customer).")
    location_id = fields.Many2one(
        related='agreement_id.location_id', store=True, string='Customer Shelf')
    template_id = fields.Many2one(
        'consignment.template', string='Campaign', copy=False,
        help="Pre-set product list. Use 'Load from Campaign' to fill the lines.")

    @api.depends('partner_id', 'company_id')
    def _compute_agreement_id(self):
        Agreement = self.env['consignment.agreement']
        for mv in self:
            mv.agreement_id = Agreement._resolve_for(mv.partner_id, mv.company_id)

    move_kind = fields.Selection([
        ('shipment', 'Shipment'),
        ('replenishment', 'Replenishment'),
        ('return', 'Return'),
        ('symbolic_renewal', 'Symbolic Renewal'),
    ], string='Type', required=True, default='shipment', tracking=True)
    is_physical = fields.Boolean(compute='_compute_is_physical')

    date = fields.Datetime(string='Date', default=fields.Datetime.now, required=True)
    line_ids = fields.One2many('consignment.move.line', 'move_id', string='Lines')
    picking_id = fields.Many2one(
        'stock.picking', string='Transfer', copy=False, readonly=True)
    picking_state = fields.Selection(related='picking_id.state', string='Transfer Status')

    # A consignment.move (CT) is a PRE-LOGISTICS COMMERCIAL document: the sales
    # team uses it to request returns (by email), track dates and send reports.
    # It does NOT move stock -- confirming only advances the commercial workflow.
    # ('done' is kept for the soc_audit adjustment, which is a real stock+value op.)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    note = fields.Text(string='Notes')

    currency_id = fields.Many2one(related='company_id.currency_id')
    amount_total = fields.Monetary(
        string='Goods Value', compute='_compute_amount_total', store=True,
        help="Merchandise value carried by the movement's fiscal note. "
             "This is not revenue -- a consignment movement is not a sale.")

    @api.depends('move_kind')
    def _compute_is_physical(self):
        for mv in self:
            mv.is_physical = mv.move_kind != 'symbolic_renewal'

    @api.depends('line_ids.price_subtotal')
    def _compute_amount_total(self):
        for mv in self:
            mv.amount_total = sum(mv.line_ids.mapped('price_subtotal'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                # Logistics layer uses the generic warehouse movement sequence.
                # The commercial "C" code lives on consignment.order (the Pedido).
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'consignment.move') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_confirm(self):
        # Commercial confirmation only. A physical movement is put on HOLD in
        # 'waiting' -- it is validated and locked, but NOT yet handed off to the
        # warehouse. The actual logistics release is action_release. A symbolic
        # renewal has no logistics, so it completes immediately.
        for mv in self:
            if mv.state != 'draft':
                continue
            if not mv.agreement_id:
                raise UserError(_(
                    "Customer %s has no consignment agreement.")
                    % mv.partner_id.display_name)
            if mv.agreement_id.state != 'active':
                raise UserError(_(
                    "Agreement %s must be active to register movements.")
                    % mv.agreement_id.name)
            if mv.move_kind == 'symbolic_renewal':
                mv._do_symbolic_renewal()
                continue
            if not mv.line_ids:
                raise UserError(_("Add at least one product line before confirming."))
            mv.state = 'waiting'

    def action_release(self):
        # Release to logistics: HANDS OFF to the warehouse. Creates the actual
        # warehouse movement (a stock.picking) and reserves it; the physical
        # validation is then the warehouse's job.
        for mv in self:
            if mv.state != 'waiting':
                continue
            picking = mv._create_picking()
            mv.picking_id = picking.id
            picking.action_confirm()
            picking.action_assign()
            mv.state = 'confirmed'

    def action_cancel(self):
        for mv in self:
            if mv.picking_id and mv.picking_id.state not in ('done', 'cancel'):
                mv.picking_id.action_cancel()
            mv.state = 'cancel'

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_apply_template(self):
        for mv in self:
            if not mv.template_id:
                raise UserError(_("Select a campaign first."))
            mv.line_ids = [(5, 0, 0)] + [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_uom_qty,
                'product_uom': line.product_id.uom_id.id,
            }) for line in mv.template_id.line_ids]

    # ------------------------------------------------------------------
    # Symbolic renewal (no physical movement)
    # ------------------------------------------------------------------
    def _do_symbolic_renewal(self):
        self.ensure_one()
        # Only renews the fiscal clock / current note. The two netting NF-es
        # (devolucao 5.918 + nova remessa 5.917) belong to soc_fiscal_br.
        self.agreement_id.message_post(body=_(
            "Symbolic renewal %s registered (no physical movement).") % self.name)
        self.state = 'done'

    # ------------------------------------------------------------------
    # Stock plumbing (never writes stock.quant directly). Confirming the CR
    # creates the picking; the warehouse then validates it to move the goods.
    # ------------------------------------------------------------------
    def _create_picking(self):
        self.ensure_one()
        picking_type, src, dest = self._get_stock_flow()
        return self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': self.partner_id.id,
            'origin': self.name,
            'location_id': src.id,
            'location_dest_id': dest.id,
            'company_id': self.company_id.id,
            'move_ids': [(0, 0, {
                'description_picking': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_uom_qty,
                'product_uom': line.product_uom.id,
                'location_id': src.id,
                'location_dest_id': dest.id,
                'company_id': self.company_id.id,
            }) for line in self.line_ids],
        })

    def _get_stock_flow(self):
        """Return (picking_type, source_location, dest_location) for the kind."""
        self.ensure_one()
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.company_id.id)], limit=1)
        if not warehouse:
            raise UserError(_("No warehouse configured for company %s.")
                            % self.company_id.display_name)
        shelf = self.agreement_id.location_id
        if not shelf:
            raise UserError(_("Agreement %s has no shelf. Activate it first.")
                            % self.agreement_id.name)
        stock = warehouse.lot_stock_id
        company = self.company_id
        if self.move_kind in ('shipment', 'replenishment'):
            picking_type = (company._get_consignment_shipment_operation_type()
                            or warehouse.int_type_id)
            return picking_type, stock, shelf
        # return: customer shelf -> warehouse, on its own "Retorno de Consignação"
        # operation type (a merchandise return, not a generic internal transfer).
        picking_type = (company._get_consignment_return_operation_type()
                        or warehouse.int_type_id)
        return picking_type, shelf, stock

    def action_view_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Transfer'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.picking_id.id,
        }

    def action_view_agreement(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Agreement'),
            'res_model': 'consignment.agreement',
            'view_mode': 'form',
            'res_id': self.agreement_id.id,
        }


class ConsignmentMoveLine(models.Model):
    _name = 'consignment.move.line'
    _description = 'Consignment Movement Line'

    move_id = fields.Many2one(
        'consignment.move', string='Movement', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain=[('type', '=', 'consu')])
    product_uom_qty = fields.Integer(string='Quantity', default=1, required=True)
    product_uom = fields.Many2one(
        'uom.uom', string='UoM', required=True,
        compute='_compute_product_uom', store=True, readonly=False, precompute=True)
    currency_id = fields.Many2one(related='move_id.currency_id')
    price_unit = fields.Float(
        string='Unit Value', compute='_compute_price_unit',
        store=True, readonly=False, precompute=True,
        help="Merchandise value per unit for the fiscal note (not a sale price).")
    price_subtotal = fields.Monetary(
        string='Subtotal', compute='_compute_price_subtotal', store=True)

    @api.depends('product_id')
    def _compute_product_uom(self):
        for line in self:
            if line.product_id and (
                    not line.product_uom
                    or line.product_uom.category_id != line.product_id.uom_id.category_id):
                line.product_uom = line.product_id.uom_id

    @api.depends('product_id')
    def _compute_price_unit(self):
        for line in self:
            if line.product_id:
                pricelist = line.move_id.agreement_id.pricelist_id
                line.price_unit = (
                    pricelist._get_product_price(line.product_id, line.product_uom_qty)
                    if pricelist else line.product_id.list_price)

    @api.depends('product_uom_qty', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.product_uom_qty * line.price_unit
