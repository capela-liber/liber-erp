# -*- coding: utf-8 -*-
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ConsignmentSettlement(models.Model):
    _name = 'consignment.settlement'
    _description = 'Consignment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

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
    agreement_state = fields.Selection(
        related='agreement_id.state', string='Agreement Status')
    agreement_valid = fields.Boolean(
        string='Valid Agreement', compute='_compute_agreement_valid',
        help="The customer has an active consignment agreement.")
    location_id = fields.Many2one(
        related='agreement_id.location_id', store=True, string='Customer Shelf')
    campaign_ids = fields.Many2many(
        'consignment.template', string='Campaigns', copy=False, readonly=True,
        help="The running campaigns of this customer's channel that were applied "
             "to this operation.")
    currency_id = fields.Many2one(related='company_id.currency_id')

    date = fields.Date(string='Settlement Date', default=fields.Date.context_today, required=True)
    stage_id = fields.Many2one(
        'consignment.settlement.stage', string='Stage',
        group_expand='_read_group_stage_ids', tracking=True, index=True, copy=False,
        default=lambda self: self.env['consignment.settlement.stage'].search([], limit=1),
        help="Work stage on the consignment board (A Fazer / Fazendo / Feito). "
             "Separate from the technical Status; this is the team's task view.")
    user_id = fields.Many2one(
        'res.users', string='Responsible', tracking=True,
        compute='_compute_user_id', store=True, readonly=False, precompute=True,
        help="Person in charge of this consignment operation. Defaults to the "
             "sales team's leader (from the contract's team), and is editable.")

    line_ids = fields.One2many(
        'consignment.settlement.line', 'settlement_id', string='Lines')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', copy=False, readonly=True)
    delivery_picking_id = fields.Many2one('stock.picking', string='Shelf Delivery', copy=False, readonly=True)
    replenishment_order_id = fields.Many2one(
        'sale.order', string='Replenishment Order', copy=False, readonly=True,
        help="The consignment Pedido (C) the dispatcher fires to refill the shelf.")
    return_move_id = fields.Many2one(
        'consignment.move', string='Return', copy=False, readonly=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Finalized'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    amount_total = fields.Monetary(
        string='Sold Amount', compute='_compute_amount_total', store=True)
    note = fields.Text(string='Notes')

    has_documents = fields.Boolean(
        string='Has Documents', compute='_compute_documents',
        help="This operation already fanned out into a sale (S), a consignment "
             "order (C) or a return (CR).")
    document_ids_summary = fields.Char(
        string='Documents', compute='_compute_documents')

    @api.depends('sale_order_id', 'replenishment_order_id', 'return_move_id',
                 'delivery_picking_id')
    def _compute_documents(self):
        for st in self:
            names = [d.name for d in (
                st.sale_order_id, st.replenishment_order_id,
                st.return_move_id, st.delivery_picking_id) if d]
            st.has_documents = bool(names)
            st.document_ids_summary = ", ".join(names)

    @api.depends('partner_id', 'company_id')
    def _compute_agreement_id(self):
        Agreement = self.env['consignment.agreement']
        for st in self:
            st.agreement_id = Agreement._resolve_for(st.partner_id, st.company_id)

    @api.depends('agreement_id.state')
    def _compute_agreement_valid(self):
        for st in self:
            st.agreement_valid = bool(st.agreement_id) and st.agreement_id.state == 'active'

    @api.depends('line_ids.price_subtotal')
    def _compute_amount_total(self):
        for st in self:
            st.amount_total = sum(st.line_ids.mapped('price_subtotal'))

    @api.onchange('partner_id')
    def _onchange_partner_id_agreement(self):
        if self.partner_id and not self.agreement_valid:
            if not self.agreement_id:
                msg = _("%s has no consignment agreement. Create and activate "
                        "one before settling.") % self.partner_id.display_name
            else:
                msg = _("The agreement %s for %s is not active (status: %s).") % (
                    self.agreement_id.name, self.partner_id.display_name,
                    self.agreement_id.state)
            return {'warning': {'title': _("No valid agreement"), 'message': msg}}

    def _ensure_valid_agreement(self):
        for st in self:
            if not st.agreement_id:
                raise UserError(_(
                    "Customer %s has no consignment agreement. A customer can "
                    "only be settled through an active agreement.")
                    % st.partner_id.display_name)
            if st.agreement_id.state != 'active':
                raise UserError(_(
                    "Agreement %s must be active to settle (current status: %s).")
                    % (st.agreement_id.name, st.agreement_id.state))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'consignment.settlement') or _('New')
        records = super().create(vals_list)
        records._subscribe_responsible()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get('user_id'):
            self._subscribe_responsible()
        return res

    def _subscribe_responsible(self):
        """Make the responsible a follower of the CO, so a customer's reply on
        the operation lands in their Discuss inbox (Diálogos)."""
        for st in self:
            if st.user_id:
                st.message_subscribe(partner_ids=st.user_id.partner_id.ids)

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        # A customer reply (incoming email from this CO's customer) also drops a
        # heads-up in the shared "Consignação — Respostas" channel.
        if (len(self) == 1 and message.message_type == 'email'
                and self.partner_id and message.author_id == self.partner_id):
            self._post_reply_to_channel()
        return message

    def _post_reply_to_channel(self):
        self.ensure_one()
        channel = self.env.ref(
            'liber_soc_settlement.channel_consignment_replies', raise_if_not_found=False)
        if not channel:
            return
        channel.message_post(
            # Markup so the record link renders as HTML (a plain str body would
            # be escaped by message_post); the customer name is escaped safely.
            body=Markup(_('💬 %(customer)s respondeu na %(co)s.')) % {
                'customer': self.partner_id.display_name,
                'co': self._get_html_link(),
            },
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Show every stage as a kanban column, even the empty ones."""
        return self.env['consignment.settlement.stage'].search([])

    @api.depends('agreement_id')
    def _compute_user_id(self):
        """Follow the sales team's leader (from the contract's team); keep any
        value already chosen."""
        for st in self:
            if not st.user_id:
                st.user_id = st.agreement_id.team_id.user_id or self.env.user

    @api.model
    @api.model
    def _blocking_draft_domain(self, partner, company):
        """A draft that is still IN THE PIPELINE blocks a new operation.

        A draft parked in a FOLDED stage ("Feito") does not. Folding is how the
        team says a column is terminal: a draft sitting there was abandoned or
        wrapped up, and it should not keep the customer from ever being settled
        again. There are 7 of those in this base, and they were silently blocking
        generation for their customers -- the wizard kept reporting "0 to create"
        and nobody could see why.
        """
        return [
            ('partner_id', '=', partner.id),
            ('company_id', '=', company.id),
            ('state', '=', 'draft'),
            # A draft with NO stage is in the pipeline too, and must block. Without
            # the OR, the join on stage_id drops it and it would vanish from the
            # rule entirely -- the quietest way to create a duplicate.
            '|', ('stage_id', '=', False), ('stage_id.fold', '=', False),
        ]

    def generate_monthly_settlements(self):
        """Monthly routine: open one draft CO per open consignment (an active
        agreement with stock on the customer's shelf), assigned to the contract's
        commercial agent. A customer whose draft is still in the pipeline is
        skipped -- never create a duplicate. One parked in a folded stage is not."""
        company = self.env.company
        agreements = self.env['consignment.agreement'].search([
            ('state', '=', 'active'),
            ('company_id', '=', company.id),
        ]).filtered(lambda a: a.on_shelf_qty > 0)
        created = 0
        for agr in agreements:
            if self.search_count(
                    self._blocking_draft_domain(agr.partner_id, company)):
                continue
            self.create({
                'partner_id': agr.partner_id.id,
                'company_id': company.id,
            })
            created += 1
        # Land back on the normal Consignments board so the breadcrumb keeps its
        # name (don't rename the view). The new CO show up in the "A Fazer" column.
        return self.env['ir.actions.act_window']._for_xml_id(
            'liber_soc_settlement.action_consignment_settlement')

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _running_campaigns(self):
        """The campaigns that apply to THIS customer: the ones running on the
        channel of their agreement. There is nothing to choose here -- the
        manager defines the campaigns, the operation executes them."""
        self.ensure_one()
        team = self.agreement_id.team_id
        if not team:
            return self.env['consignment.template']
        return self.env['consignment.template'].search([
            ('is_running', '=', True), ('team_id', '=', team.id),
        ])

    def action_apply_campaigns(self):
        """Overlay every running campaign of the customer's channel as the target
        assortment.

        The campaign is NOT a replacement for the map: it is how many copies each
        title should end up with. A title already on the shelf gets its target;
        a title missing from the map is added as a brand new placement.

        CONFLICT RULE (decided by the business): when two running campaigns of the
        same channel ask for the same title with different targets, THE HIGHEST
        TARGET WINS. It is the only rule that never shrinks an assortment when two
        campaigns overlap.
        """
        self.ensure_one()
        self._ensure_valid_agreement()
        campaigns = self._running_campaigns()
        if not campaigns:
            raise UserError(_(
                "No campaign is running on this customer's channel (%s).",
                self.agreement_id.team_id.name or _("no channel on the agreement")))

        targets = {}
        for line in campaigns.line_ids:
            pid = line.product_id.id
            targets[pid] = max(targets.get(pid, 0), line.product_uom_qty)

        pricelist = self.agreement_id.pricelist_id
        existing = {line.product_id.id: line for line in self.line_ids}
        new_lines = []
        out_of_stock = self.env['product.product']
        for product_id, target in targets.items():
            product = self.env['product.product'].browse(product_id)
            line = existing.get(product_id)
            if not line and not self._on_hand(product):
                # A title the customer does not have AND we do not have either:
                # the campaign has nothing to place. Adding the line would create
                # a row whose only content is a red zero -- noise the operator has
                # to read and dismiss, on every title we are out of.
                # A title already ON the map is kept: it is on the shelf, so the
                # acerto still matters even if we cannot refill it.
                out_of_stock |= product
                continue
            price = (pricelist._get_product_price(product, target)
                     if pricelist else product.list_price)
            if line:
                # The target is stored, not the resulting quantity: the
                # replenishment is a live compute (see _compute_qty_replenish), so
                # it follows the operator as they type what the customer sold.
                line.qty_target = target
                if not line.price_unit:
                    line.price_unit = price
            else:
                new_lines.append((0, 0, {
                    'product_id': product.id,
                    'qty_reported': 0,
                    'price_unit': price,
                    'qty_target': target,
                }))
        if new_lines:
            self.line_ids = new_lines
        self.campaign_ids = [(6, 0, campaigns.ids)]
        self.env.flush_all()   # so qty_replenish / qty_short are computed below

        if out_of_stock:
            # Say what was dropped. A campaign that silently places 12 of its 40
            # titles reads as "applied" when it did a third of the job.
            self.message_post(body=Markup(
                _("<b>%(n)s title(s) of the campaign were not placed: we have "
                  "none in stock.</b><br/>%(names)s")) % {
                    'n': len(out_of_stock),
                    'names': Markup("<br/>").join(
                        out_of_stock.mapped('display_name')),
                })

        # And write it down where the MANAGER will read it: on the campaign.
        # From the CO, a campaign that shipped 60 of the 400 copies it asked for
        # still looks "applied". From the campaign, it has to look like what it
        # is -- a campaign the warehouse could not feed.
        placed = self.line_ids.filtered(lambda l: l.qty_target > 0)
        for campaign in campaigns:
            wanted = campaign.line_ids.product_id
            mine = placed.filtered(lambda l: l.product_id in wanted)
            campaign._log_application(
                self, len(mine),
                mine.filtered(lambda l: l.qty_short > 0),
                out_of_stock & wanted)

    def _on_hand(self, product):
        """Our own warehouse stock of a title, the hard limit on what can be sent."""
        self.ensure_one()
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', (self.company_id or self.env.company).id)], limit=1)
        if not warehouse:
            return 0
        return int(product.with_context(
            location=warehouse.lot_stock_id.id).qty_available)

    def _shelf_quantities(self, products):
        """Current stock on this customer's shelf, per product."""
        self.ensure_one()
        res = defaultdict(int)
        shelf = self.location_id
        if shelf and products:
            for q in self.env['stock.quant'].search([
                    ('location_id', '=', shelf.id),
                    ('product_id', 'in', products.ids)]):
                res[q.product_id.id] += int(q.quantity)
        return res

    def _record_shortfalls(self):
        """Write down every way this operation missed a campaign target, by cause.

        Called at run, once the map is frozen and before the baixa moves the
        shelf: the numbers must be the ones the operation settled against.

        Three causes are visible here (the fourth, ``tempo``, is the ABSENCE of
        an operation and can only be seen by the cron):

        - ``estoque``  needed more than we have AND more than is inbound.
        - ``manual``   we had the stock, the operator sent less than the target.
        - ``falta``    a campaign was running on the channel and was never applied.
        """
        self.ensure_one()
        Short = self.env['consignment.shortfall']
        team = self.agreement_id.team_id
        applied = self.campaign_ids
        skipped = self._running_campaigns() - applied
        products = self.line_ids.product_id | skipped.line_ids.product_id
        facts = Short._stock_facts(self.company_id, products)
        base = {
            'partner_id': self.partner_id.id,
            'settlement_id': self.id,
            'team_id': team.id if team else False,
            'company_id': self.company_id.id,
            'date': self.date,
        }
        vals = []
        # --- estoque + manual: on titles a campaign targeted -----------------
        for line in self.line_ids.filtered(lambda l: l.qty_target > 0):
            needed = line.qty_target - (line.qty_on_shelf - line.qty_reported)
            if needed <= 0:
                continue
            f = facts.get(line.product_id.id, {'on_hand': 0, 'incoming': 0})
            on_hand, incoming = f['on_hand'], f['incoming']
            campaign = Short._owning_campaign(applied, line.product_id)
            common = dict(
                base, product_id=line.product_id.id,
                campaign_id=campaign.id or False,
                qty_target=line.qty_target, qty_on_shelf=line.qty_on_shelf,
                qty_on_hand=on_hand, qty_incoming=incoming)
            # Out of stock: what neither today's stock nor inbound POs can cover.
            stock_gap = max(needed - (on_hand + incoming), 0)
            if stock_gap:
                vals.append(dict(common, nature='estoque', qty_short=stock_gap))
            # Manual: stock alone could have placed min(needed, on_hand); the
            # operator sent less than that. Only the part stock could have
            # covered is the person's doing -- the rest is estoque, above.
            manual_gap = max(min(needed, on_hand) - line.qty_replenish, 0)
            if manual_gap:
                vals.append(dict(common, nature='manual', qty_short=manual_gap))
        # --- falta: a running campaign of the channel was never applied ------
        if skipped:
            shelf = self._shelf_quantities(skipped.line_ids.product_id)
            for camp in skipped:
                for cline in camp.line_ids:
                    on_shelf = shelf.get(cline.product_id.id, 0)
                    gap = cline.product_uom_qty - on_shelf
                    if gap <= 0:
                        continue
                    f = facts.get(cline.product_id.id, {'on_hand': 0, 'incoming': 0})
                    vals.append(dict(
                        base, nature='falta', product_id=cline.product_id.id,
                        campaign_id=camp.id, qty_target=cline.product_uom_qty,
                        qty_on_shelf=on_shelf, qty_on_hand=f['on_hand'],
                        qty_incoming=f['incoming'], qty_short=gap))
        Short._sync_for_settlement(self, vals)

    def action_populate_from_shelf(self):
        self.ensure_one()
        self._ensure_valid_agreement()
        if not self.location_id:
            raise UserError(_("The agreement has no shelf. Activate it first."))
        self.line_ids.unlink()
        quants = self.env['stock.quant'].search([
            ('location_id', '=', self.location_id.id), ('quantity', '>', 0)])
        pricelist = self.agreement_id.pricelist_id
        aggregated = {}
        for quant in quants:
            aggregated.setdefault(quant.product_id, 0.0)
            aggregated[quant.product_id] += quant.quantity
        vals = []
        for product, qty in aggregated.items():
            price = pricelist._get_product_price(product, qty) if pricelist else product.list_price
            # qty_on_shelf is computed live while draft -- no snapshot to write here.
            vals.append((0, 0, {
                'product_id': product.id,
                'price_unit': price,
            }))
        self.line_ids = vals

    def _open_overstock_wizard(self, over_lines):
        self.ensure_one()
        summary = "\n".join(
            _("- %(product)s: replenish %(rep)s, on hand %(oh)s",
              product=l.product_id.display_name, rep=l.qty_replenish, oh=l.qty_on_hand)
            for l in over_lines)
        wizard = self.env['consignment.run.overstock.wizard'].create({
            'settlement_id': self.id,
            'summary': summary,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Not enough stock'),
            'res_model': 'consignment.run.overstock.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }

    def action_draft(self):
        """Back to draft -- but only if this operation never fanned out.

        A cancelled CO that DID generate documents cannot be reopened. Its S / C /
        CR were cancelled, but the links to them survive, and action_run only
        creates a sale `if not st.sale_order_id`. Reopening such a CO and running
        it again would therefore create NOTHING, silently, because it believes the
        documents already exist. The operator would watch a Run do nothing and have
        no way to know why. Open a new CO instead: the cancelled one is history.
        """
        for st in self:
            if st.document_ids_summary:
                raise UserError(_(
                    "%(co)s already generated documents (%(docs)s) and cannot go "
                    "back to draft. They were cancelled, but this operation still "
                    "points at them, so running it again would create nothing. "
                    "Open a new operation.",
                    co=st.name, docs=st.document_ids_summary))
        self.write({'state': 'draft'})

    def action_cancel(self):
        """Cancel the operation and cascade to the documents it generated."""
        for st in self:
            cancelled = []
            so = st.sale_order_id
            if so and so.state != 'cancel':
                so.sudo().action_cancel()
                cancelled.append(so.name)
            pick = st.delivery_picking_id
            if pick and pick.state not in ('done', 'cancel'):
                pick.action_cancel()
                cancelled.append(pick.name)
            rep = st.replenishment_order_id
            if rep and rep.state != 'cancel':
                rep.sudo().action_cancel()
                cancelled.append(rep.name)
            ret = st.return_move_id
            if ret and ret.state != 'cancel':
                ret.action_cancel()
                cancelled.append(ret.name)
            if cancelled:
                st.message_post(body=_(
                    "Consignment cancelled. Documents cancelled: %s")
                    % ", ".join(cancelled))
            st.state = 'cancel'

    def action_run(self):
        """The single dispatcher of the operation ("Run").

        From one screen it fans out into the correctly-typed documents:
        - Reported > 0  -> a real sale.order + shelf baixa (this IS a sale).
        - Replenish > 0 -> a consignment.move (remessa; NOT a sale, just a
          movement with a note).
        - Return > 0    -> a consignment.move (devolucao; pure stock, not a sale).
        Any combination may be present. A replenish-only run is a pure shipment /
        first placement (nothing sold yet).
        """
        for st in self:
            if st.state != 'draft':
                continue
            st._ensure_valid_agreement()
            if not st.line_ids:
                raise UserError(_("Load the map before running the operation."))
            sold = st.line_ids.filtered(lambda l: l.qty_reported > 0)
            to_replenish = st.line_ids.filtered(lambda l: l.qty_replenish > 0)
            to_return = st.line_ids.filtered(lambda l: l.qty_return > 0)
            if not sold and not to_replenish and not to_return:
                raise UserError(_(
                    "Nothing to do: no sales reported, no replenishment and no "
                    "return planned."))
            over = to_replenish.filtered(lambda l: l.qty_replenish > l.qty_on_hand)
            if over:
                return st._open_overstock_wizard(over)
            # Pin the map BEFORE any document is created: the sale and return
            # moves below are about to take stock off the shelf, and the map we
            # keep must be the one the operator settled against -- not the shelf
            # as it looks after the baixa.
            st.line_ids._freeze_map()
            # Record the rupture BEFORE the baixa: the shelf is about to drop by
            # what was sold, and the miss must be measured against the map the
            # operation actually settled, not the shelf as it looks afterwards.
            st._record_shortfalls()
            if sold and not st.sale_order_id:
                st.sale_order_id = st._create_sale_order(sold)
                st.delivery_picking_id = st._create_shelf_outflow(sold)
            if to_replenish and not st.replenishment_order_id:
                st.replenishment_order_id = st._create_replenishment_order(to_replenish)
            if to_return and not st.return_move_id:
                st.return_move_id = st._create_return_move(to_return)
            st.state = 'confirmed'

    # ------------------------------------------------------------------
    # Finalization: a confirmed operation closes once every document it
    # fanned out to has finished its logistics / invoicing. The three
    # branches (see the map): CO -> S -> WH (sale delivered & invoiced),
    # CO -> C -> WH (replenishment Pedido delivered), CO -> CR -> RET
    # (return transfer validated). A cron finalizes them automatically;
    # the Finalize button lets a user close one by hand.
    # ------------------------------------------------------------------
    def _logistics_closed(self):
        self.ensure_one()
        # CO -> S -> WH : the sale's shelf delivery is validated and there
        # is nothing left to invoice (the fiscal note is issued).
        so = self.sale_order_id
        if so and so.state != 'cancel' and so.invoice_status not in ('invoiced', 'no'):
            return False
        pick = self.delivery_picking_id
        if pick and pick.state not in ('done', 'cancel'):
            return False
        # CO -> C -> WH : the replenishment Pedido is confirmed and fully delivered.
        rep = self.replenishment_order_id
        if rep and rep.state != 'cancel':
            if rep.state not in ('sale', 'done'):
                return False
            pickings = rep.picking_ids
            if not pickings or any(p.state not in ('done', 'cancel') for p in pickings):
                return False
        # CO -> CR -> RET : the return transfer is validated.
        ret = self.return_move_id
        if ret and ret.state != 'cancel':
            if not ret.picking_id or ret.picking_id.state != 'done':
                return False
        return True

    def _finalize_if_closed(self):
        for st in self.filtered(lambda s: s.state == 'confirmed'):
            if st._logistics_closed():
                st.state = 'done'
                st.message_post(body=_(
                    "Consignment finalized: all logistics and invoicing closed."))

    @api.model
    def _cron_finalize_closed(self):
        """Auto-finalize confirmed operations whose documents have all closed.
        Finalization is fully automatic -- there is no manual Finalize button."""
        self.search([('state', '=', 'confirmed')])._finalize_if_closed()

    # ------------------------------------------------------------------
    # Sale + stock
    # ------------------------------------------------------------------
    def _create_sale_order(self, sold_lines):
        self.ensure_one()
        so_vals = {
            'partner_id': self.partner_id.id,
            'origin': self.name,
            'consignment_operation_id': self.id,
            # Stamped at birth. A sale happens LATER, on another document, and no
            # live calculation can attribute it back to the campaign afterwards:
            # whatever goes out unstamped can never be attributed to anything.
            'campaign_ids': [(6, 0, self.campaign_ids.ids)],
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_reported,
                'price_unit': line.price_unit,
                'discount': line.discount,
            }) for line in sold_lines],
        }
        if self.agreement_id.pricelist_id:
            so_vals['pricelist_id'] = self.agreement_id.pricelist_id.id
        return self.env['sale.order'].create(so_vals)

    def _create_shelf_outflow(self, sold_lines):
        self.ensure_one()
        # A dedicated operation type (ACERTO/), NOT the warehouse delivery type
        # (WH/OUT): the acerto only draws down the customer's shelf, it is not a
        # warehouse job, so it must not land in the warehouse's Delivery Orders.
        picking_type = self.company_id._get_consignment_settlement_operation_type()
        customers = self.env.ref('stock.stock_location_customers')
        shelf = self.location_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': self.partner_id.id,
            'origin': self.name,
            'location_id': shelf.id,
            'location_dest_id': customers.id,
            'company_id': self.company_id.id,
            'move_ids': [(0, 0, {
                'description_picking': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_reported,
                'product_uom': line.product_id.uom_id.id,
                'location_id': shelf.id,
                'location_dest_id': customers.id,
                'company_id': self.company_id.id,
            }) for line in sold_lines],
        })
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
        picking.with_context(skip_backorder=True).button_validate()
        return picking

    def _create_replenishment_order(self, to_send):
        """Fire a consignment Pedido (sale.order C) to refill the shelf.

        The dispatcher creates a *Pedido*, not a bare movement -- left in draft
        so the commercial team can review/edit/confirm it. It is a consignment
        order (is_consignment), never a sale."""
        self.ensure_one()
        return self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'is_consignment': True,
            'consignment_type': 'replenishment',
            'consignment_operation_id': self.id,
            'origin': self.name,
            # On a replenishment the stamp is exact: these copies are going out
            # BECAUSE of these campaigns.
            'campaign_ids': [(6, 0, self.campaign_ids.ids)],
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_replenish,
            }) for line in to_send],
        })

    def _create_return_move(self, to_return):
        """Build the physical return movement (devolucao; not a sale).

        Case 1 only: recalling unsold consignment stock. It never sold, so
        there is nothing to reverse financially -- pure reverse stock move
        (shelf -> warehouse).
        """
        self.ensure_one()
        return self.env['consignment.move'].create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'move_kind': 'return',
            'consignment_operation_id': self.id,
            'note': _("Return from consignment %s") % self.name,
            'line_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_return,
                'product_uom': line.product_id.uom_id.id,
                'price_unit': line.price_unit,
            }) for line in to_return],
        })

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlements'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

    def action_view_replenishment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Order'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.replenishment_order_id.id,
        }

    def action_view_return(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return'),
            'res_model': 'consignment.move',
            'view_mode': 'form',
            'res_id': self.return_move_id.id,
        }

    def action_send_map(self):
        """Open the email composer to send the consignment map PDF to the
        customer and the contract's report recipients (report_contact_ids)."""
        self.ensure_one()
        template = self.env.ref(
            'liber_soc_settlement.mail_template_consignment_map', raise_if_not_found=False)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Map'),
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_model': 'consignment.settlement',
                'default_res_ids': self.ids,
                'default_template_id': template.id if template else False,
                'default_composition_mode': 'comment',
            },
        }

    def action_send_map_batch(self):
        """Batch-send the map to the SELECTED operations (Actions menu), each to
        its own recipients (customer + contract report contacts). Sends directly
        (no composer). Operations whose recipients have no e-mail are skipped."""
        template = self.env.ref(
            'liber_soc_settlement.mail_template_consignment_map', raise_if_not_found=False)
        sent = 0
        skipped = self.browse()
        for co in self:
            recipients = co.partner_id | co.agreement_id.report_contact_ids
            if not template or not any(r.email for r in recipients):
                skipped |= co
                continue
            template.send_mail(co.id, force_send=False)
            sent += 1
        message = _('%s map(s) queued for sending.') % sent
        if skipped:
            message += _(' %(n)s skipped (no e-mail): %(names)s',
                         n=len(skipped), names=', '.join(skipped.mapped('name')))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Send Map'),
                'message': message,
                'type': 'warning' if skipped else 'success',
                'sticky': bool(skipped),
            },
        }


class ConsignmentSettlementLine(models.Model):
    _name = 'consignment.settlement.line'
    _description = 'Consignment Settlement Line'

    settlement_id = fields.Many2one(
        'consignment.settlement', string='Settlement', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='settlement_id.currency_id')
    # Stored so the shortfall can be PIVOTED. "Faltou: 1.489" tells nobody
    # anything: the question is always WHICH customer, WHICH title, and whether
    # it is chronic or a one-off. A measure without axes is not a measure.
    partner_id = fields.Many2one(
        related='settlement_id.partner_id', string='Customer',
        store=True, index=True)
    date = fields.Date(related='settlement_id.date', string='Date', store=True)
    team_id = fields.Many2one(
        related='settlement_id.agreement_id.team_id', string='Sales Channel',
        store=True)
    campaign_ids = fields.Many2many(
        related='settlement_id.campaign_ids', string='Campaigns')
    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain=[('type', '=', 'consu')])
    qty_on_hand = fields.Integer(
        string='On Hand', compute='_compute_qty_on_hand',
        help="Our warehouse stock available to replenish this title. "
             "Don't suggest replenishing what we don't have.")
    # The ONE number the day-to-day operator needs. It reads Odoo's own
    # settlements first, and only falls back to the imported NFe when this title
    # was never settled here -- never both, or the same sale would be counted
    # twice once Odoo starts emitting the note itself.
    # The movement breakdown (opening / sent / sold / returned / turnover) used
    # to live here as five more columns; it now lives in the Shelf Ledger, which
    # is where a movement analysis belongs. This line is for running the acerto.
    qty_recent_sales = fields.Integer(
        string='Sales', compute='_compute_qty_recent_sales',
        help="Units THIS customer sold within the analysis window (see "
             "Settings): the settlements run in Odoo, or -- for a title never "
             "settled here yet -- what the imported NFe says. "
             "Click to see the composing sale orders.")
    sale_order_ids = fields.Many2many(
        'sale.order', compute='_compute_qty_recent_sales',
        string='Recent Sale Orders')
    # The map used to be a snapshot taken when the CO was generated, and it went
    # stale the moment anything else moved on the shelf: the operator could be
    # settling against a picture from hours ago. Now it is live while the CO is
    # a draft, and freezes when the CO is run -- from then on it is the map that
    # was actually sent to the customer, so past COs keep telling the truth.
    qty_on_shelf = fields.Integer(
        string='Map', compute='_compute_qty_on_shelf',
        help="Stock at the customer. Live while the operation is a draft; "
             "frozen once it is run (the map the customer was sent).")
    qty_on_shelf_frozen = fields.Integer(
        string='Map (frozen)', readonly=True, copy=False,
        help="The map as it stood when the operation was run.")
    qty_reported = fields.Integer(
        string='Settled', default=0,
        help="Quantity the customer reported as sold. This is the settlement.")
    qty_replenish = fields.Integer(
        string='Place', compute='_compute_qty_replenish',
        store=True, readonly=False,
        help="Quantity to resend to refill the shelf. Suggested equal to what "
             "was reported sold; editable.")
    qty_target = fields.Integer(
        string='Target', readonly=True, copy=False,
        help="How many copies of this title the running campaigns of this "
             "customer's channel want on the shelf. Set by 'Apply Campaigns'; "
             "empty means no campaign asks for this title.")
    qty_short = fields.Integer(
        string='Short', compute='_compute_qty_replenish', store=True,
        help="What the shelf needed and we could not send, because we do not have "
             "it in stock. Zero means the campaign was fully placed.")
    qty_return = fields.Integer(
        string='Return', default=0,
        help="Quantity to recall from the shelf (no turnover). Pure stock "
             "movement back to the warehouse; never a sale.")
    price_unit = fields.Float(
        string='Unit Price', compute='_compute_price_unit',
        store=True, readonly=False, precompute=True)
    discount = fields.Float(
        string='Disc.%', compute='_compute_discount',
        store=True, readonly=False, precompute=True,
        help="Inherited from the agreement's default discount; editable per line.")
    price_subtotal = fields.Monetary(
        string='Subtotal', compute='_compute_price_subtotal', store=True)

    # Health of the consigned title: how long since it last settled (acerto) for
    # this customer. Never settled -> measured from when it hit the shelf.
    shelf_status = fields.Selection([
        ('ok', 'Ok'),
        ('attention', 'Attention'),
        ('critical', 'Critical'),
        ('no_return', 'No Return'),
    ], string='Shelf Status', compute='_compute_shelf_status',
        help="Ok / Attention / Critical / No Return by days since this title's "
             "last settlement (acerto). Thresholds in the Consignment settings.")
    days_since_settlement = fields.Integer(
        string='Days', compute='_compute_shelf_status',
        help="Days since this title's last settlement (acerto) for this customer. "
             "Never settled: counted from when it hit the shelf.")
    last_settlement_date = fields.Date(
        string='Last Settlement', compute='_compute_shelf_status')
    # NOTE: the movement breakdown (Opening / Sent / Sold / Returned / Turnover /
    # To Reconcile) lived here as six computed columns and was removed on
    # 12/07/2026. It was analysis, not operation: the person running an acerto
    # needs the map, the sales and the three quantities to type -- not a ledger.
    # That analysis now lives in the Shelf Ledger (consignment.ledger), where it
    # belongs, with periods and pivot. Removing it also drops a per-settlement
    # stock.move search from every read of this list.

    def init(self):
        """One-off: the map was a plain stored column before it became a
        compute. Carry every existing value over to the frozen column so the
        history of past COs (and their PDFs) is preserved."""
        self.env.cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'consignment_settlement_line'
              AND column_name = 'qty_on_shelf'
        """)
        if self.env.cr.fetchone():
            self.env.cr.execute("""
                UPDATE consignment_settlement_line
                SET qty_on_shelf_frozen = qty_on_shelf
                WHERE qty_on_shelf IS NOT NULL
                  AND COALESCE(qty_on_shelf_frozen, 0) = 0
            """)

    # Deliberately NOT triggered by qty_on_shelf_frozen: the switch to the frozen
    # map is what leaving draft means, and 'settlement_id.state' already fires it.
    # If the frozen WRITE also invalidated this field, it would cascade into
    # qty_replenish (which depends on the map) mid-run and silently revert the
    # operator's manual send back to the suggested one -- the bug that made the
    # 'manual' ruptura impossible to even observe.
    @api.depends('product_id', 'settlement_id.state', 'settlement_id.location_id')
    def _compute_qty_on_shelf(self):
        """Live from the shelf while draft; the frozen map afterwards."""
        Quant = self.env['stock.quant']
        for st, lines in self._lines_by_settlement().items():
            if st.state != 'draft':
                for line in lines:
                    line.qty_on_shelf = line.qty_on_shelf_frozen
                continue
            shelf = st.location_id
            on_shelf = defaultdict(float)
            if shelf:
                for q in Quant.search([('location_id', '=', shelf.id),
                                       ('product_id', 'in', lines.product_id.ids)]):
                    on_shelf[q.product_id.id] += q.quantity
            for line in lines:
                line.qty_on_shelf = int(on_shelf.get(line.product_id.id, 0))

    def _freeze_map(self):
        """Pin the map as it stands now -- called when the CO leaves draft."""
        for line in self:
            line.qty_on_shelf_frozen = line.qty_on_shelf

    @api.depends('product_id')
    def _compute_qty_on_hand(self):
        Warehouse = self.env['stock.warehouse']
        wh_cache = {}
        for line in self:
            company = line.settlement_id.company_id or self.env.company
            wh = wh_cache.get(company.id)
            if wh is None:
                wh = Warehouse.search([('company_id', '=', company.id)], limit=1)
                wh_cache[company.id] = wh
            if line.product_id and wh:
                product = line.product_id.with_context(location=wh.lot_stock_id.id)
                line.qty_on_hand = int(product.qty_available)
            else:
                line.qty_on_hand = 0

    def _lines_by_settlement(self):
        groups = defaultdict(lambda: self.env['consignment.settlement.line'])
        for line in self:
            groups[line.settlement_id] += line
        return groups

    def _xml_fiscal_facts(self, partner, company, product_ids, window_start=False):
        """Per product, the fiscal facts from the imported XMLs (nfe.xml) for
        this customer: last effective-sale date, first shipment date, sale qty
        in the window and total qty ever shipped. One search over the customer's
        consignment panels. Read-only -- touches no stock. Lets the CO reflect
        history that only exists as imported NFes (no Odoo settlements yet)."""
        facts = {pid: {'last_sale': False, 'first_ship': False,
                       'sales_window': 0.0, 'total_ship': 0.0}
                 for pid in product_ids}
        if not partner or not product_ids:
            return facts
        company_id = company.id if company else self.env.company.id
        panels = self.env['nfe.xml.panel'].search([
            ('partner_id', '=', partner.id),
            ('company_id', '=', company_id),
            ('is_cancelled', '=', False),
            ('cfop_id.consignment_effect', 'in', ('sale', 'ship')),
        ])
        pset = set(product_ids)
        for panel in panels:
            effect = panel.cfop_id.consignment_effect
            pdate = panel.file_create_date
            for item in panel.panel_items:
                pid = item.ks_product_id.id
                if pid not in pset:
                    continue
                qty = item.ks_product_qty or 0.0
                f = facts[pid]
                if effect == 'sale':
                    if pdate and (not f['last_sale'] or pdate > f['last_sale']):
                        f['last_sale'] = pdate
                    if pdate and (not window_start or pdate >= window_start):
                        f['sales_window'] += qty
                else:  # ship
                    f['total_ship'] += qty
                    if pdate and (not f['first_ship'] or pdate < f['first_ship']):
                        f['first_ship'] = pdate
        return facts

    @api.depends('product_id', 'settlement_id.partner_id')
    def _compute_qty_recent_sales(self):
        months = int(self.env['ir.config_parameter'].sudo().get_param(
            'soc_settlement.sales_window_months', '3') or 3)
        start = fields.Date.context_today(self) - relativedelta(months=months)
        Line = self.env['consignment.settlement.line']
        self.qty_recent_sales = 0
        self.sale_order_ids = False
        for st, lines in self._lines_by_settlement().items():
            partner = st.partner_id
            if not partner:
                continue
            company = st.company_id or self.env.company
            pids = lines.mapped('product_id').ids
            # Odoo settlements in the window (batched, grouped by product).
            odoo_qty = defaultdict(float)
            odoo_so = defaultdict(lambda: self.env['sale.order'])
            for ol in Line.search([
                    ('product_id', 'in', pids), ('qty_reported', '>', 0),
                    # 'done' is a settlement that already closed (sold, shipped
                    # and invoiced) -- it is MORE of a sale than 'confirmed', not
                    # less. Leaving it out silently shrank Sales and Turnover.
                    ('settlement_id.state', 'in', ('confirmed', 'done')),
                    ('settlement_id.date', '>=', start),
                    ('settlement_id.partner_id', '=', partner.id),
                    ('settlement_id.company_id', '=', company.id)]):
                odoo_qty[ol.product_id.id] += ol.qty_reported
                odoo_so[ol.product_id.id] |= ol.settlement_id.sale_order_id
            xml = self._xml_fiscal_facts(partner, company, pids, start)
            for line in lines:
                pid = line.product_id.id
                if not pid:
                    # A blank line (no product yet, e.g. one just added in the
                    # form) has no sales to total, and its False id was never put
                    # in `pids`, so `xml` has no key for it -- guard the lookup.
                    line.qty_recent_sales = 0
                    line.sale_order_ids = self.env['sale.order']
                    continue
                oq = int(odoo_qty.get(pid, 0))
                # Fiscal XML sales fill in when there is no Odoo settlement yet.
                line.qty_recent_sales = oq or int(xml.get(pid, {}).get('sales_window', 0))
                line.sale_order_ids = odoo_so.get(pid, self.env['sale.order'])

    @api.model
    def _shelf_thresholds(self):
        icp = self.env['ir.config_parameter'].sudo()
        return (
            int(icp.get_param('soc_settlement.shelf_ok_days', 45) or 45),
            int(icp.get_param('soc_settlement.shelf_attention_days', 60) or 60),
            int(icp.get_param('soc_settlement.shelf_critical_days', 120) or 120),
        )

    @api.model
    def _shelf_bucket(self, days, thresholds):
        ok, att, crit = thresholds
        return ('ok' if days <= ok else 'attention' if days <= att
                else 'critical' if days <= crit else 'no_return')

    @api.model
    def _shelf_anchors(self, partner, company, shelf, product_ids,
                       exclude_settlement=None):
        """Per product, the date the shelf clock starts from.

        Anchor = the most recent acerto for THIS customer, whether it was settled
        in Odoo or only exists as an imported NFe. A title never settled falls
        back to when it hit the shelf (fiscal first shipment, else the quant's
        arrival) -- otherwise a title that never sold would look brand new.

        Shared by the CO line and the On Shelf report on purpose: two copies of
        this rule would drift, and then the same title would show two ages.
        """
        anchors = {}
        if not partner or not product_ids:
            return anchors
        Line = self.env['consignment.settlement.line']
        Quant = self.env['stock.quant']
        domain = [
            ('product_id', 'in', product_ids), ('qty_reported', '>', 0),
            ('settlement_id.state', 'in', ('confirmed', 'done')),
            ('settlement_id.partner_id', '=', partner.id),
            ('settlement_id.company_id', '=', company.id),
        ]
        if exclude_settlement:
            domain.append(('settlement_id', '!=', exclude_settlement.id))
        odoo_last = defaultdict(lambda: False)
        for ol in Line.search(domain):
            d = ol.settlement_id.date
            if d and (not odoo_last[ol.product_id.id] or d > odoo_last[ol.product_id.id]):
                odoo_last[ol.product_id.id] = d
        xml = self._xml_fiscal_facts(partner, company, product_ids)
        # Oldest shelf quant per product (very last fallback).
        quant_first = {}
        if shelf:
            for q in Quant.search([
                    ('location_id', '=', shelf.id), ('product_id', 'in', product_ids),
                    ('quantity', '>', 0)], order='in_date asc'):
                if q.product_id.id not in quant_first and q.in_date:
                    quant_first[q.product_id.id] = fields.Date.to_date(q.in_date)
        for pid in product_ids:
            xf = xml[pid]
            dates = [d for d in (odoo_last.get(pid), xf['last_sale']) if d]
            anchor = max(dates) if dates else (xf['first_ship'] or quant_first.get(pid))
            if anchor:
                anchors[pid] = anchor
        return anchors

    @api.depends('product_id', 'settlement_id.partner_id')
    def _compute_shelf_status(self):
        thresholds = self._shelf_thresholds()
        today = fields.Date.context_today(self)
        self.last_settlement_date = False
        self.days_since_settlement = 0
        self.shelf_status = False
        for st, lines in self._lines_by_settlement().items():
            partner = st.partner_id
            if not partner:
                continue
            company = st.company_id or self.env.company
            anchors = self._shelf_anchors(
                partner, company, st.agreement_id.location_id,
                lines.mapped('product_id').ids, exclude_settlement=st)
            for line in lines:
                if not line.product_id:
                    continue
                anchor = anchors.get(line.product_id.id)
                if not anchor:
                    continue
                days = (today - anchor).days
                line.last_settlement_date = anchor
                line.days_since_settlement = days
                line.shelf_status = self._shelf_bucket(days, thresholds)

    def action_view_recent_sales(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recent sales of %s') % self.product_id.display_name,
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.sale_order_ids.ids)],
        }

    @api.depends('product_id')
    def _compute_price_unit(self):
        for line in self:
            if line.product_id:
                pricelist = line.settlement_id.agreement_id.pricelist_id
                line.price_unit = (
                    pricelist._get_product_price(line.product_id, 1)
                    if pricelist else line.product_id.list_price)

    @api.depends('settlement_id.agreement_id')
    def _compute_discount(self):
        for line in self:
            line.discount = line.settlement_id.agreement_id.discount

    @api.depends('qty_reported', 'qty_target', 'qty_on_shelf', 'settlement_id.state')
    def _compute_qty_replenish(self):
        """How much to send: what the shelf needs, capped by what we actually have.

        Two different things, and the code used to confuse them.

        WHAT THE SHELF NEEDS. With a campaign target, the shelf must END at the
        target, and the acerto is exactly what LEAVES the shelf:

            on the shelf after the acerto = Map - Reported
            needed                        = Target - (Map - Reported)

        (The old code did `Target - Map` and ignored the acerto, so it undershot by
        precisely what the customer had sold: map 10, target 100, sold 10 left the
        shelf empty and sent only 90 -- ending at 90, below the target, always.)
        Without a campaign there is no target and the old default stands: resend
        what was sold, keeping the shelf where it was.

        WHAT WE HAVE. On Hand is not advice, it is the world: we cannot ship a book
        that does not exist. So the campaign places WHAT IT CAN -- needed, capped at
        On Hand. Never a plan we know is impossible.

        The cap is not silent: Target shows what was wanted, Short shows what we
        could not send, and the cell turns orange.
        """
        for line in self:
            if line.settlement_id.state != 'draft':
                # Pinned once the operation leaves draft. What the operator chose
                # to send is a decision, not a live suggestion: recomputing it
                # here (the frozen map fires this compute at run) would revert a
                # manual under-send and ship a quantity nobody asked for. Keep
                # the stored values -- the map is history now.
                line.qty_replenish = line.qty_replenish
                line.qty_short = line.qty_short
                continue
            if line.qty_target:
                needed = line.qty_target - (line.qty_on_shelf - line.qty_reported)
            else:
                needed = line.qty_reported
            line.qty_replenish = max(min(needed, line.qty_on_hand), 0)
            line.qty_short = max(needed - line.qty_replenish, 0)

    @api.depends('qty_reported', 'price_unit', 'discount')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = (
                line.qty_reported * line.price_unit * (1 - (line.discount or 0.0) / 100.0))

    @api.onchange('qty_return', 'qty_replenish', 'qty_reported')
    def _onchange_quantities(self):
        """Immediate guards on the three action columns:
        - can't return more than what's on the shelf after the sale (clamp);
        - never return AND replenish the same title -> net them.

        There is NO stock warning here any more. It used to pop a blocking modal
        whenever the replenishment exceeded On Hand -- which, since campaigns set
        the replenishment by themselves, meant a modal on EVERY line: the operator
        typed "1" in the acerto and got hit with a lecture about the warehouse,
        which is not the question they were answering.

        Nothing is lost. `action_run` already stops on the same condition, through
        the overstock wizard, and that is the moment it actually decides something
        -- when you ask to execute. Here it is shown, not shouted: the
        replenishment cell turns red when we do not have the stock.
        """
        warning = None
        remaining = self.qty_on_shelf - self.qty_reported
        if self.qty_return > remaining:
            self.qty_return = max(remaining, 0)
            warning = {
                'title': _("Return too high"),
                'message': _(
                    "%(product)s: you can return at most %(rem)s (shelf %(map)s "
                    "minus %(rep)s reported sold). Adjusted to %(rem)s.",
                    product=self.product_id.display_name,
                    rem=max(remaining, 0), map=self.qty_on_shelf,
                    rep=self.qty_reported)}
        if self.qty_return > 0 and self.qty_replenish > 0:
            net = min(self.qty_return, self.qty_replenish)
            self.qty_return -= net
            self.qty_replenish -= net
        if warning:
            return {'warning': warning}

    # qty_on_shelf is computed and not stored, so it cannot be a constrains
    # trigger; the two fields the operator types are enough to catch this.
    @api.constrains('qty_return', 'qty_reported')
    def _check_qty_return(self):
        for line in self:
            remaining = max(line.qty_on_shelf - line.qty_reported, 0)
            if line.qty_return > remaining:
                raise ValidationError(_(
                    "%(product)s: cannot return %(ret)s. Only %(rem)s remain on "
                    "the shelf after the reported sale.",
                    product=line.product_id.display_name,
                    ret=line.qty_return, rem=remaining))
