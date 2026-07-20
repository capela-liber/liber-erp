# -*- coding: utf-8 -*-
from collections import defaultdict

from markupsafe import Markup

from odoo import api, fields, models
from odoo.fields import Domain


class ConsignmentTemplate(models.Model):
    """The template stops being a bag of products and becomes a campaign.

    Three things were missing for it to be usable as "the necessary catalogue":

    - WHO it is for. A single global assortment is useless: a children's
      bookshop and an academic one do not need the same titles. The audience is
      the SALES CHANNEL (crm.team) -- and the link already existed, on the
      agreement (consignment.agreement.team_id), which is where the channel must
      be read from: res.partner.team_id no longer exists in Odoo 19.
    - WHEN it runs. A campaign has a window; outside it, it suggests nothing.
    - Whether it is still ALIVE. `active` already existed on the model; it was
      simply never exposed, so nobody could archive a finished campaign.

    Conflict rule, decided by the business: when two live templates of the same
    channel ask for the same title with different targets, THE HIGHEST TARGET
    WINS. It is the only rule that never shrinks an assortment when two campaigns
    overlap (summing would inflate without control; "most recent wins" could
    knock down a campaign that is still running).

    Curating one title at a time is fine for a correction and awful for building
    a list. Odoo already solved this: `product.catalog.mixin` is the same catalog
    Sales and Purchase use -- you browse the titles and bump quantities, and they
    land as lines. No home-made wizard, no extra button of ours.
    """
    _name = 'consignment.template'
    _inherit = ['consignment.template', 'product.catalog.mixin', 'mail.thread']

    code = fields.Char(
        string='Code', readonly=True, copy=False, index=True,
        help="Unique reference of the campaign (CP/year/NNNN). The NAME is not an "
             "identity: two campaigns can be called the same thing, and this base "
             "already has two 'Orides'. Everything the campaign generates carries "
             "this code, so its results can be traced back to it.")
    team_id = fields.Many2one(
        'crm.team', string='Sales Channel',
        help="The channel this assortment is for. A customer belongs to a "
             "channel through their agreement, so the template reaches the "
             "customer via the contract -- not via the partner.")
    date_start = fields.Date(string='From')
    date_end = fields.Date(string='To')
    is_running = fields.Boolean(
        string='Running', compute='_compute_is_running', store=True,
        help="Active, and within its window. Only running templates define the "
             "target assortment of a shelf.")
    partner_count = fields.Integer(
        string='Customers', compute='_compute_partner_count',
        help="Customers reached by this template: those whose ACTIVE agreement "
             "is on this channel.")

    # Many2many, not One2many: an operation applies EVERY running campaign of the
    # channel, so one order can be driven by more than one of them.
    order_ids = fields.Many2many(
        'sale.order', 'sale_order_campaign_rel', 'campaign_id', 'order_id',
        string='Orders', readonly=True,
        help="Every order this campaign put out: the replenishments it drove, and "
             "the sales of the operations it was applied to.")
    order_count = fields.Integer(compute='_compute_order_count', string='# Orders')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self.env['ir.sequence'].next_by_code(
                    'consignment.campaign') or '/'
        return super().create(vals_list)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for campaign in self:
            campaign.display_name = (
                "%s — %s" % (campaign.code, campaign.name)
                if campaign.code and campaign.name else (campaign.name or ''))

    def _compute_order_count(self):
        for campaign in self:
            campaign.order_count = len(campaign.order_ids)

    def action_view_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Orders of %s', self.code or self.name),
            'res_model': 'sale.order',
            'domain': [('id', 'in', self.order_ids.ids)],
            'view_mode': 'list,form',
            'context': {'create': False},
        }

    @api.depends('active', 'date_start', 'date_end')
    def _compute_is_running(self):
        today = fields.Date.context_today(self)
        for tmpl in self:
            tmpl.is_running = bool(
                tmpl.active
                and (not tmpl.date_start or tmpl.date_start <= today)
                and (not tmpl.date_end or tmpl.date_end >= today))

    @api.depends('team_id')
    def _compute_partner_count(self):
        Agreement = self.env['consignment.agreement']
        for tmpl in self:
            tmpl.partner_count = Agreement.search_count([
                ('state', '=', 'active'), ('team_id', '=', tmpl.team_id.id),
            ]) if tmpl.team_id else 0

    def action_view_partners(self):
        self.ensure_one()
        agreements = self.env['consignment.agreement'].search([
            ('state', '=', 'active'), ('team_id', '=', self.team_id.id)])
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Customers of %s', self.team_id.name or ''),
            'res_model': 'res.partner',
            'domain': [('id', 'in', agreements.partner_id.ids)],
            'view_mode': 'list,form',
            'context': {'create': False},
        }

    # ------------------------------------------------------------------
    # What the campaign could NOT deliver
    # ------------------------------------------------------------------
    def _shortfall_records(self):
        """Every ruptura attributed to THIS campaign, of every nature.

        The attribution is stamped on each row (campaign_id) when it is recorded,
        by the same HIGHEST-TARGET-WINS rule the operation uses -- so two
        campaigns of one channel no longer take the blame for the same copies
        (they once both reported the same 782 short)."""
        self.ensure_one()
        if not self.id:
            return self.env['consignment.shortfall']
        return self.env['consignment.shortfall'].search([
            ('campaign_id', '=', self.id)])

    qty_short_total = fields.Integer(
        string='Short', compute='_compute_qty_short_total',
        help="Copies of this campaign's target that were not placed, of every "
             "nature -- out of stock, sent short by hand, campaign skipped, or "
             "overdue. The campaign failing, not the demand.")

    def _compute_qty_short_total(self):
        groups = self.env['consignment.shortfall']._read_group(
            [('campaign_id', 'in', self.ids)], ['campaign_id'],
            ['qty_short:sum'])
        totals = {campaign.id: total for campaign, total in groups}
        for tmpl in self:
            tmpl.qty_short_total = totals.get(tmpl.id, 0)

    def action_view_shortfall(self):
        """Opens the Ruptura report, scoped to this campaign: the same measure,
        with axes. A number alone answers nothing."""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'liber_soc_settlement.action_shortfall')
        action['name'] = self.env._('Ruptura: %s', self.display_name)
        action['domain'] = [('campaign_id', '=', self.id)]
        action['context'] = {'search_default_g_nature': 1}
        return action

    def _log_application(self, settlement, placed, short_lines, not_placed):
        """Write down what this campaign actually managed to do on one operation.

        The manager reads the campaign, not the acerto. A campaign that asked for
        400 copies and shipped 60 looks "applied" from the CO -- from here it has
        to look like what it is: a campaign the warehouse could not feed.
        """
        self.ensure_one()
        short_total = sum(line.qty_short for line in short_lines)
        body = [self.env._(
            "<b>Applied to %(co)s</b> (%(customer)s): %(placed)s title(s) placed.",
            co=settlement.name, customer=settlement.partner_id.display_name,
            placed=placed)]
        if short_total:
            body.append(self.env._(
                "<b>%(units)s copy(ies) short across %(n)s title(s)</b> "
                "-- not enough stock:", units=short_total, n=len(short_lines)))
            body.append("<ul>%s</ul>" % "".join(
                self.env._("<li>%(title)s: wanted %(want)s, sent %(sent)s, "
                           "short %(short)s (on hand %(oh)s)</li>",
                           title=line.product_id.display_name,
                           want=line.qty_target, sent=line.qty_replenish,
                           short=line.qty_short, oh=line.qty_on_hand)
                for line in short_lines))
        if not_placed:
            body.append(self.env._(
                "<b>%(n)s title(s) not placed at all</b> -- none in stock: "
                "%(names)s", n=len(not_placed),
                names=", ".join(not_placed.mapped('display_name'))))
        if not short_total and not not_placed:
            body.append(self.env._("Fully supplied."))
        self.message_post(body=Markup("<br/>".join(body)))

    # ------------------------------------------------------------------
    # Overdue: the target nobody is pursuing any more (nature 'tempo')
    # ------------------------------------------------------------------
    @api.model
    def _campaign_stale_days(self):
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'soc_settlement.campaign_stale_days', 30) or 30)

    @api.model
    def _cron_flag_overdue(self):
        """A running campaign can fail silently: its customers simply stop being
        settled, so nobody ever applies the target and the shelf drifts below it.
        No event fires when that happens -- it is the ABSENCE of an event -- so a
        clock has to notice.

        Each night: for every running campaign, every active customer on its
        channel whose last acerto is older than the tolerated window (a setting,
        default 30 days) has a 'tempo' rupture opened for each title still short
        of target. The rows are cron-owned and rebuilt from scratch every run, so
        a customer settled today drops off the list on its own.
        """
        Short = self.env['consignment.shortfall']
        Settlement = self.env['consignment.settlement']
        Agreement = self.env['consignment.agreement']
        Quant = self.env['stock.quant']
        threshold = self._campaign_stale_days()
        today = fields.Date.context_today(self)
        running = self.search([('is_running', '=', True)])
        # Cron owns every 'tempo' row: wipe and recompute, never accumulate.
        Short.search([('nature', '=', 'tempo'),
                      ('campaign_id', 'in', running.ids)]).unlink()
        vals = []
        for camp in running:
            if not camp.team_id or not camp.line_ids:
                continue
            agreements = Agreement.search([
                ('state', '=', 'active'), ('team_id', '=', camp.team_id.id),
                ('company_id', '=', camp.company_id.id)])
            products = camp.line_ids.product_id
            facts = Short._stock_facts(camp.company_id, products)
            for agr in agreements:
                last = Settlement.search([
                    ('partner_id', '=', agr.partner_id.id),
                    ('company_id', '=', camp.company_id.id),
                    ('state', 'in', ('confirmed', 'done'))],
                    order='date desc', limit=1)
                anchor = last.date if last else agr.date_start
                if not anchor or (today - anchor).days <= threshold:
                    continue
                on_shelf = defaultdict(int)
                if agr.location_id:
                    for q in Quant.search([
                            ('location_id', '=', agr.location_id.id),
                            ('product_id', 'in', products.ids)]):
                        on_shelf[q.product_id.id] += int(q.quantity)
                for cline in camp.line_ids:
                    gap = cline.product_uom_qty - on_shelf.get(cline.product_id.id, 0)
                    if gap <= 0:
                        continue
                    f = facts.get(cline.product_id.id, {'on_hand': 0, 'incoming': 0})
                    vals.append({
                        'nature': 'tempo',
                        'date': today,
                        'partner_id': agr.partner_id.id,
                        'product_id': cline.product_id.id,
                        'team_id': camp.team_id.id,
                        'campaign_id': camp.id,
                        'company_id': camp.company_id.id,
                        'qty_target': cline.product_uom_qty,
                        'qty_on_shelf': on_shelf.get(cline.product_id.id, 0),
                        'qty_on_hand': f['on_hand'],
                        'qty_incoming': f['incoming'],
                        'qty_short': gap,
                    })
        if vals:
            Short.create(vals)

    # ------------------------------------------------------------------
    # Product catalog (product.catalog.mixin)
    # ------------------------------------------------------------------
    def _get_product_catalog_domain(self):
        """The catalogue only ever offers the universe. Curation happens INSIDE
        it, whichever door you come in through."""
        return super()._get_product_catalog_domain() & Domain(
            'soc_consignable', '=', True)

    def _get_product_catalog_record_lines(self, product_ids, **kwargs):
        grouped = defaultdict(lambda: self.env['consignment.template.line'])
        for line in self.line_ids.filtered(
                lambda l: l.product_id.id in product_ids):
            grouped[line.product_id] |= line
        return grouped

    def _get_product_catalog_order_data(self, products, **kwargs):
        res = super()._get_product_catalog_order_data(products, **kwargs)
        for product in products:
            # No pricing on an assortment: the price comes from the agreement.
            # The list price is shown only so the curator has a sense of value.
            res[product.id]['price'] = product.list_price
        return res

    def _update_order_line_info(self, product_id, quantity, **kwargs):
        """The catalogue's + / - lands here: create, update, or drop the line."""
        self.ensure_one()
        line = self.line_ids.filtered(lambda l: l.product_id.id == product_id)
        if line:
            if quantity:
                line.product_uom_qty = quantity
            else:
                # Back to zero in the catalogue means "not in this assortment".
                line.unlink()
        elif quantity:
            self.env['consignment.template.line'].create({
                'template_id': self.id,
                'product_id': product_id,
                'product_uom_qty': quantity,
            })
        return self.env['product.product'].browse(product_id).list_price


class ConsignmentTemplateLine(models.Model):
    """Curation happens inside the universe, never outside it."""
    _inherit = 'consignment.template.line'

    def _get_product_catalog_lines_data(self, **kwargs):
        """What the catalogue shows for a title already in the assortment."""
        if len(self) == 1:
            return {
                'quantity': self.product_uom_qty,
                'price': self.product_id.list_price,
                'readOnly': False,
                'uomDisplayName': self.product_id.uom_id.display_name,
            }
        if self:
            # Two lines for the same title should not exist; if they do, show the
            # total and lock it rather than silently editing one of them.
            return {
                'quantity': sum(self.mapped('product_uom_qty')),
                'price': self[0].product_id.list_price,
                'readOnly': True,
                'uomDisplayName': self[0].product_id.uom_id.display_name,
            }
        return {'quantity': 0, 'price': 0.0, 'uomDisplayName': ''}

    # ------------------------------------------------------------------
    # Coverage: can the warehouse feed this target across every shelf?
    # ------------------------------------------------------------------
    # The question the manager cannot answer from the campaign today: "100 in
    # stock, target 10, twenty customers -- I can only serve half." A target per
    # shelf is meaningless without the number of shelves and the stock behind it.
    # This is the balance, netted against what is already inbound (forecast), so
    # a title arriving next week does not read as a shortage.
    team_id = fields.Many2one(
        related='template_id.team_id', string='Sales Channel')
    campaign_code = fields.Char(related='template_id.code', string='Campaign Code')
    is_running = fields.Boolean(related='template_id.is_running')
    # Stored, and refreshed nightly by a cron -- the same choice the shelf age
    # makes, and for the same reason: coverage moves when STOCK moves and when a
    # new customer signs, and no @api.depends on this line can see either. A
    # planning report reads yesterday's warehouse; storing it also lets the
    # report sort, filter and group by "Will Short", which a live compute cannot.
    coverage_shelves = fields.Integer(
        string='Shelves', compute='_compute_coverage', store=True,
        help="Active customers on this campaign's channel: the shelves the "
             "target must reach.")
    coverage_needed = fields.Integer(
        string='Needed', compute='_compute_coverage', store=True,
        help="Target per shelf x number of shelves: the total this campaign "
             "asks the warehouse for.")
    coverage_on_hand = fields.Integer(
        string='On Hand', compute='_compute_coverage', store=True)
    coverage_incoming = fields.Integer(
        string='Inbound', compute='_compute_coverage', store=True,
        help="Copies already on the way (open purchases).")
    coverage_short = fields.Integer(
        string='Will Short', compute='_compute_coverage', store=True,
        help="Needed minus what we have and what is inbound: what this campaign "
             "cannot cover unless more is printed/bought.")
    coverage_pct = fields.Float(
        string='Coverage %', compute='_compute_coverage', store=True,
        help="Share of the total need that today's stock plus inbound covers.")
    coverage_shelves_served = fields.Integer(
        string='Shelves Served', compute='_compute_coverage', store=True,
        help="How many shelves the stock (plus inbound) can bring to target. "
             "100 on hand, target 10 -> 10 shelves; the rest go short.")

    @api.depends('product_uom_qty', 'product_id',
                 'template_id.team_id', 'template_id.company_id')
    def _compute_coverage(self):
        Short = self.env['consignment.shortfall']
        Agreement = self.env['consignment.agreement']
        by_company = defaultdict(lambda: self.env['product.product'])
        for line in self:
            company = line.template_id.company_id or self.env.company
            by_company[company.id] |= line.product_id
        facts_cache = {
            cid: Short._stock_facts(self.env['res.company'].browse(cid), prods)
            for cid, prods in by_company.items()}
        shelf_cache = {}
        for line in self:
            company = line.template_id.company_id or self.env.company
            team = line.template_id.team_id
            key = (company.id, team.id)
            if key not in shelf_cache:
                shelf_cache[key] = Agreement.search_count([
                    ('state', '=', 'active'), ('team_id', '=', team.id),
                    ('company_id', '=', company.id)]) if team else 0
            shelves = shelf_cache[key]
            target = line.product_uom_qty
            f = facts_cache.get(company.id, {}).get(
                line.product_id.id, {'on_hand': 0, 'incoming': 0})
            available = f['on_hand'] + f['incoming']
            needed = target * shelves
            line.coverage_shelves = shelves
            line.coverage_needed = needed
            line.coverage_on_hand = f['on_hand']
            line.coverage_incoming = f['incoming']
            line.coverage_short = max(needed - available, 0)
            line.coverage_pct = (
                100.0 if needed <= 0 else min(available, needed) / needed * 100.0)
            line.coverage_shelves_served = available // target if target else 0

    @api.model
    def _cron_refresh_coverage(self):
        """Recompute the stored coverage of running campaigns.

        Stock and the customer base drift with no write on this line to notice
        it, so the stored value goes stale on its own -- refreshed on a clock,
        exactly like the shelf age. Only running campaigns matter: an archived or
        future one is not a plan anyone is about to execute."""
        lines = self.search([('template_id.is_running', '=', True)])
        if lines:
            lines.invalidate_recordset([
                'coverage_shelves', 'coverage_needed', 'coverage_on_hand',
                'coverage_incoming', 'coverage_short', 'coverage_pct',
                'coverage_shelves_served'])
            lines._compute_coverage()
            lines.flush_recordset()

    # Shown while curating: you cannot judge an assortment without seeing what
    # each title IS. The publication date separates a launch from backlist, and
    # that decision is the whole point of building the list.
    publish_date = fields.Date(
        related='product_id.product_tmpl_id.metabooks_publish_date',
        string='Published', readonly=True)
    isbn = fields.Char(related='product_id.default_code', string='ISBN', readonly=True)
    availability_id = fields.Many2one(
        related='product_id.product_tmpl_id.metabooks_product_availability',
        string='Availability', readonly=True)
    categ_id = fields.Many2one(
        related='product_id.categ_id', string='Category', readonly=True)
    soc_consignable = fields.Boolean(
        related='product_id.soc_consignable', readonly=True)
