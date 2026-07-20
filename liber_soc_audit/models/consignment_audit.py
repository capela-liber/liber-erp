# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_round

# CFOP effects that feed the shelf equation.
_SHELF_EFFECTS = ('ship', 'sale', 'return')


class ConsignmentAudit(models.Model):
    """Rebuild the expected shelf balance from the fiscal history and confront
    it with the map.

    A standalone document keyed by customer (+ company); the agreement is only
    a reference/shortcut, the audit does not live inside any contract. It reads
    the already-parsed nfe.xml.panel / nfe.xml.items records (never re-parses
    the XML), classifies each item by its CFOP effect, aggregates per product,
    and lets the user accept the difference item by item or in toto -- which
    materialises a consignment.move of the ``adjustment`` kind that brings the
    shelf to the accepted quantity.
    """
    _name = 'consignment.audit'
    _description = 'Consignment Audit (XML vs Map)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_to desc, id desc'

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
    agreement_id = fields.Many2one(
        'consignment.agreement', string='Agreement',
        compute='_compute_agreement_id', store=True, readonly=True,
        help="Resolved from the customer (one agreement per customer). Only a "
             "reference -- the audit does not live inside the contract.")
    location_id = fields.Many2one(
        related='agreement_id.location_id', string='Customer Shelf')

    date_from = fields.Date(
        string='From', tracking=True,
        help="Start of the fiscal series. Leave empty to go back to the very "
             "first NFe of this customer.")
    date_to = fields.Date(
        string='To', default=fields.Date.context_today, required=True,
        tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('computed', 'Computed'),
        ('under_review', 'Under Review'),
        ('accepted', 'Accepted'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)

    line_ids = fields.One2many(
        'consignment.audit.line', 'audit_id', string='Lines')

    # --- coverage / quality indicators (see "hard parts" in the spec) --------
    coverage_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('partial', 'Partial'),
        ('complete', 'Complete'),
    ], string='Series Coverage', default='unknown', tracking=True,
        help="Whether ALL of the customer's consignment NFes are imported. The "
             "audit only closes reliably on a complete series -- set this once "
             "the gaps below are reviewed.")
    panel_count = fields.Integer(
        string='NFes Considered', readonly=True,
        help="Non-cancelled consignment NFes that fed this audit.")
    unmatched_item_count = fields.Integer(
        string='Unmatched Items', readonly=True,
        help="Fiscal items whose product could not be matched (EAN outside the "
             "catalogue). They are NOT counted in any line -- resolve them "
             "(alias/catalogue) and recompute.")
    unmatched_qty = fields.Float(
        string='Unmatched Qty', readonly=True)
    unmapped_cfop_ids = fields.Many2many(
        'nfe.cfop', 'consignment_audit_unmapped_cfop_rel',
        'audit_id', 'cfop_id', string='Unmapped CFOPs', readonly=True,
        help="CFOPs found on this customer's notes in the period that have no "
             "consignment effect configured. Map them (Settings > CFOP) if any "
             "is a consignment movement, then recompute.")
    no_cfop_panel_count = fields.Integer(
        string='Notes Without CFOP', readonly=True,
        help="Notes in the period whose CFOP is not recorded (not parsed, or "
             "the CFOP code is missing from the CFOP table). They are NOT "
             "counted -- seed the CFOP and relink, then recompute.")

    adjustment_move_id = fields.Many2one(
        'consignment.move', string='Adjustment', copy=False, readonly=True)
    diff_count = fields.Integer(
        string='Divergences', compute='_compute_counters', store=True)
    line_count = fields.Integer(
        string='Products', compute='_compute_counters', store=True)
    note = fields.Text(string='Notes')

    @api.depends('partner_id', 'company_id')
    def _compute_agreement_id(self):
        Agreement = self.env['consignment.agreement']
        for audit in self:
            audit.agreement_id = Agreement._resolve_for(
                audit.partner_id, audit.company_id)

    @api.depends('line_ids', 'line_ids.line_state')
    def _compute_counters(self):
        for audit in self:
            audit.line_count = len(audit.line_ids)
            audit.diff_count = len(
                audit.line_ids.filtered(lambda l: l.line_state == 'divergent'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'consignment.audit') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Reconciliation engine (reads parsed panels; never re-parses XML)
    # ------------------------------------------------------------------
    def _panel_domain(self):
        self.ensure_one()
        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('is_cancelled', '=', False),
            ('company_id', '=', self.company_id.id),
        ]
        if self.date_from:
            domain.append(('file_create_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('file_create_date', '<=', self.date_to))
        return domain

    def _reconcile(self):
        """Return the per-product fiscal aggregate + quality buckets.

        {
          'products': {product_id: {'ship','sale','return','panels': set}},
          'panel_count': int,
          'unmatched_item_count': int, 'unmatched_qty': float,
          'unmapped_cfops': set(cfop_id),
        }
        """
        self.ensure_one()
        panels = self.env['nfe.xml.panel'].search(self._panel_domain())
        products = {}
        counted_panels = set()
        unmatched_count = 0
        unmatched_qty = 0.0
        unmapped_cfops = set()
        no_cfop_panels = 0
        for panel in panels:
            effect = panel.cfop_id.consignment_effect
            if effect not in _SHELF_EFFECTS:
                # Not classified as a consignment movement:
                # - no CFOP at all (not parsed / not in the CFOP table) -> a
                #   completeness risk, counted separately so nothing is dropped
                #   silently;
                # - a CFOP with no effect -> flag it so the user can map it;
                # - an explicit 'ignore' -> silent, on purpose.
                if not panel.cfop_id:
                    no_cfop_panels += 1
                elif not effect:
                    unmapped_cfops.add(panel.cfop_id.id)
                continue
            counted_panels.add(panel.id)
            pdate = panel.file_create_date
            for item in panel.panel_items:
                qty = item.ks_product_qty or 0.0
                if not item.ks_product_id:
                    unmatched_count += 1
                    unmatched_qty += qty
                    continue
                rec = products.setdefault(
                    item.ks_product_id.id,
                    {'ship': 0.0, 'sale': 0.0, 'return': 0.0, 'panels': set(),
                     'last_sale': False, 'first_ship': False})
                rec[effect] += qty
                rec['panels'].add(panel.id)
                # Anchor dates for the health tag: newest sale (acerto), oldest
                # shipment (fallback for a title that never settled).
                if pdate:
                    if effect == 'sale' and (not rec['last_sale'] or pdate > rec['last_sale']):
                        rec['last_sale'] = pdate
                    elif effect == 'ship' and (not rec['first_ship'] or pdate < rec['first_ship']):
                        rec['first_ship'] = pdate
        return {
            'products': products,
            'panel_count': len(counted_panels),
            'unmatched_item_count': unmatched_count,
            'unmatched_qty': unmatched_qty,
            'unmapped_cfops': unmapped_cfops,
            'no_cfop_panels': no_cfop_panels,
        }

    def _shelf_map(self):
        """Current on-shelf quantity per product (the map)."""
        self.ensure_one()
        result = {}
        if not self.location_id:
            return result
        quants = self.env['stock.quant'].search([
            ('location_id', '=', self.location_id.id)])
        for quant in quants:
            result.setdefault(quant.product_id.id, 0.0)
            result[quant.product_id.id] += quant.quantity
        return result

    def _bucket_shelf_status(self, days):
        """Same title-health scale as the CO map, driven by the shared
        thresholds in Settings. `days` = age against the anchor date."""
        if days is None:
            return False
        icp = self.env['ir.config_parameter'].sudo()
        ok = int(icp.get_param('soc_settlement.shelf_ok_days', 45) or 45)
        att = int(icp.get_param('soc_settlement.shelf_attention_days', 60) or 60)
        crit = int(icp.get_param('soc_settlement.shelf_critical_days', 120) or 120)
        if days <= ok:
            return 'ok'
        if days <= att:
            return 'attention'
        if days <= crit:
            return 'critical'
        return 'no_return'

    def action_compute(self):
        # Re-resolve the agreement link: the stored compute only depends on the
        # audit's own partner/company, so a contract created/activated AFTER the
        # audit leaves it stale (None) -> no shelf, empty map, accept fails.
        self._compute_agreement_id()
        for audit in self:
            if audit.state == 'accepted':
                raise UserError(_(
                    "This audit is already accepted. Reset it to draft to "
                    "recompute."))
            audit.line_ids.unlink()
            data = audit._reconcile()
            shelf = audit._shelf_map()
            product_ids = set(data['products']) | set(shelf)
            today = fields.Date.context_today(audit)
            lines = []
            for pid in product_ids:
                agg = data['products'].get(pid, {})
                last_sale = agg.get('last_sale')
                anchor = last_sale or agg.get('first_ship')
                days = (today - anchor).days if anchor else None
                lines.append((0, 0, {
                    'product_id': pid,
                    'qty_shipped_xml': agg.get('ship', 0.0),
                    'qty_sold_xml': agg.get('sale', 0.0),
                    'qty_returned_xml': agg.get('return', 0.0),
                    'qty_map': shelf.get(pid, 0.0),
                    'panel_ids': [(6, 0, list(agg.get('panels', ())))],
                    'last_settlement_date': last_sale or False,
                    'days_since_settlement': days or 0,
                    'shelf_status': audit._bucket_shelf_status(days),
                }))
            audit.write({
                'line_ids': lines,
                'panel_count': data['panel_count'],
                'unmatched_item_count': data['unmatched_item_count'],
                'unmatched_qty': data['unmatched_qty'],
                'unmapped_cfop_ids': [(6, 0, list(data['unmapped_cfops']))],
                'no_cfop_panel_count': data['no_cfop_panels'],
                'state': 'computed',
            })
            audit.message_post(body=_(
                "Audit computed: %(panels)s NFes, %(lines)s products, "
                "%(diffs)s divergences.",
                panels=data['panel_count'], lines=len(lines),
                diffs=len(audit.line_ids.filtered(
                    lambda l: l.line_state == 'divergent'))))
        return True

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    # ------------------------------------------------------------------
    # Accept (item by item or in toto) + materialise the adjustment
    # ------------------------------------------------------------------
    def _set_review(self):
        for audit in self.filtered(lambda a: a.state == 'computed'):
            audit.state = 'under_review'

    def action_accept_all_fiscal(self):
        """In toto: accept the fiscal (XML) balance on every line.

        A negative fiscal balance (more sales than shipments recorded -> an
        incomplete series) is floored at zero: a shelf cannot hold a negative
        quantity. The true (possibly negative) value stays visible in Expected.
        """
        for audit in self:
            for line in audit.line_ids:
                line.resolution = 'accept_fiscal'
                line.accepted_qty = max(line.qty_expected, 0.0)
            audit._set_review()

    def action_accept_all_map(self):
        """In toto: keep the map on every line (no shelf change)."""
        for audit in self:
            for line in audit.line_ids:
                line.resolution = 'accept_map'
                line.accepted_qty = line.qty_map
            audit._set_review()

    def action_accept(self):
        """Materialise the accepted differences into one adjustment movement.

        Every divergent line must be resolved. The accepted quantity per
        product minus the current map yields a signed delta; a single
        consignment.move of kind 'adjustment' applies them (found stock or
        shrinkage), routing the value to the configured account.
        """
        rounding = 1.0  # books are whole units
        for audit in self:
            if audit.state not in ('computed', 'under_review'):
                raise UserError(_(
                    "Compute the audit before accepting it."))
            unresolved = audit.line_ids.filtered(
                lambda l: l.line_state == 'divergent' and not l.resolution)
            if unresolved:
                raise UserError(_(
                    "%d divergent line(s) are still unresolved. Accept them "
                    "(fiscal/map/manual) or use one of the 'Accept all' "
                    "buttons.") % len(unresolved))
            # A shelf cannot hold a negative quantity: the accepted target is
            # floored at zero. A negative fiscal balance means the series is
            # incomplete (more sales than shipments imported) -- flag it.
            negative = audit.line_ids.filtered(lambda l: l.accepted_qty < 0)
            if negative:
                audit.message_post(body=_(
                    "%d title(s) had a negative fiscal balance (sales exceed "
                    "shipments -- likely missing shipment XMLs or an opening "
                    "balance). Their shelf was floored at zero: %s",
                    len(negative),
                    ", ".join(negative.mapped('product_id.display_name')[:10])))
            move_lines = []
            for line in audit.line_ids:
                target = max(line.accepted_qty, 0.0)
                delta = int(float_round(
                    target - line.qty_map, precision_rounding=rounding))
                if delta:
                    move_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'product_uom_qty': abs(delta),
                        'product_uom': line.product_id.uom_id.id,
                        'adjustment_delta': delta,
                    }))
            if move_lines:
                if not audit.agreement_id or not audit.location_id:
                    raise UserError(_(
                        "%s has no active consignment shelf. Activate the "
                        "agreement before adjusting/initialising the map.")
                        % audit.partner_id.display_name)
                move = self.env['consignment.move'].create({
                    'partner_id': audit.partner_id.id,
                    'company_id': audit.company_id.id,
                    'move_kind': 'adjustment',
                    'audit_id': audit.id,
                    'note': _("Shelf adjustment from audit %s") % audit.name,
                    'line_ids': move_lines,
                })
                move.action_confirm()
                audit.adjustment_move_id = move.id
                audit.message_post(body=_(
                    "Shelf adjusted from audit: movement "
                    "<a href=# data-oe-model=consignment.move data-oe-id=%(id)d>"
                    "%(name)s</a> (%(n)d product(s)).",
                    id=move.id, name=move.name, n=len(move_lines)))
            else:
                audit.message_post(body=_(
                    "Audit accepted with no shelf change (map already matches "
                    "the accepted balance)."))
            audit.state = 'accepted'
        return True

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------
    def action_view_adjustment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Adjustment'),
            'res_model': 'consignment.move',
            'view_mode': 'form',
            'res_id': self.adjustment_move_id.id,
        }

    def action_view_shelf(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shelf Stock'),
            'res_model': 'stock.quant',
            'view_mode': 'list,form',
            'domain': [('location_id', '=', self.location_id.id)],
        }


class ConsignmentAuditLine(models.Model):
    _name = 'consignment.audit.line'
    _description = 'Consignment Audit Line'
    _order = 'line_state, product_id'

    audit_id = fields.Many2one(
        'consignment.audit', string='Audit', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='audit_id.company_id', store=True)
    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain=[('type', '=', 'consu')])

    # Fiscal aggregates (rebuilt from the XMLs), driven by CFOP effect.
    qty_opening = fields.Float(
        string='Opening', default=0.0,
        help="Known shelf balance before the fiscal series starts. Use it when "
             "the imported series begins after the real relationship did.")
    qty_shipped_xml = fields.Float(string='Shipped', readonly=True)
    qty_sold_xml = fields.Float(string='Sold', readonly=True)
    qty_returned_xml = fields.Float(string='Returned', readonly=True)
    qty_expected = fields.Float(
        string='Expected', compute='_compute_qty_expected', store=True,
        help="Fiscal shelf balance = opening + shipped - sold - returned.")
    qty_map = fields.Float(
        string='Map', readonly=True,
        help="Current on-shelf balance (the map).")
    qty_diff = fields.Float(
        string='Difference', compute='_compute_qty_diff', store=True,
        help="Expected (fiscal) - map. Positive: fiscal says more is on the "
             "shelf than the map; negative: the opposite (shrinkage).")

    # Same title-health scale as the CO map, but the last-settlement date is
    # reconstructed from the XMLs (most recent 'sale' NFe). Snapshot at compute.
    last_settlement_date = fields.Date(
        string='Last Settlement', readonly=True,
        help="Date of the most recent effective-sale NFe (acerto) for this "
             "title, reconstructed from the imported XMLs.")
    days_since_settlement = fields.Integer(
        string='Days Since Settlement', readonly=True)
    shelf_status = fields.Selection([
        ('ok', 'Ok'),
        ('attention', 'Attention'),
        ('critical', 'Critical'),
        ('no_return', 'No Return'),
    ], string='Shelf Status', readonly=True,
        help="Ok / Attention / Critical / No Return by days since this title's "
             "last settlement in the XMLs (never settled -> from first "
             "shipment). Same thresholds as the CO map (Consignment settings).")

    line_state = fields.Selection([
        ('match', 'Match'),
        ('divergent', 'Divergent'),
        ('accepted', 'Accepted'),
    ], string='State', compute='_compute_line_state', store=True)
    resolution = fields.Selection([
        ('accept_fiscal', 'Accept XML'),
        ('accept_map', 'Accept Map'),
        ('manual', 'Manual'),
    ], string='Resolution')
    accepted_qty = fields.Float(
        string='Accepted', help="Shelf balance to settle on when the audit is "
                                 "accepted.")
    adjustment_delta = fields.Float(
        string='Adjustment', compute='_compute_adjustment_delta',
        help="Accepted - map: what the adjustment movement will apply.")
    note = fields.Char(string='Note')
    panel_ids = fields.Many2many(
        'nfe.xml.panel', 'consignment_audit_line_nfe_xml_rel',
        'line_id', 'panel_id', string='Fiscal Documents',
        help="The NFes that fed this line -- the audit trail.")
    panel_count = fields.Integer(compute='_compute_panel_count')

    @api.depends('qty_opening', 'qty_shipped_xml', 'qty_sold_xml', 'qty_returned_xml')
    def _compute_qty_expected(self):
        for line in self:
            line.qty_expected = (
                line.qty_opening + line.qty_shipped_xml
                - line.qty_sold_xml - line.qty_returned_xml)

    @api.depends('qty_expected', 'qty_map')
    def _compute_qty_diff(self):
        for line in self:
            line.qty_diff = line.qty_expected - line.qty_map

    @api.depends('qty_diff', 'resolution')
    def _compute_line_state(self):
        for line in self:
            if line.resolution:
                line.line_state = 'accepted'
            elif float_compare(line.qty_diff, 0.0, precision_rounding=0.001) == 0:
                line.line_state = 'match'
            else:
                line.line_state = 'divergent'

    @api.depends('accepted_qty', 'qty_map')
    def _compute_adjustment_delta(self):
        for line in self:
            line.adjustment_delta = line.accepted_qty - line.qty_map

    @api.depends('panel_ids')
    def _compute_panel_count(self):
        for line in self:
            line.panel_count = len(line.panel_ids)

    @api.onchange('resolution')
    def _onchange_resolution(self):
        for line in self:
            if line.resolution == 'accept_fiscal':
                line.accepted_qty = max(line.qty_expected, 0.0)
            elif line.resolution == 'accept_map':
                line.accepted_qty = line.qty_map
            # 'manual' keeps whatever the user typed.

    def action_view_panels(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fiscal Documents of %s') % self.product_id.display_name,
            'res_model': 'nfe.xml.panel',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.panel_ids.ids)],
        }
