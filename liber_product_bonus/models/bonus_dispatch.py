# -*- coding: utf-8 -*-
from odoo import _, api, fields, models

from .bonus_rating import SCORE_HELP
from odoo.exceptions import UserError

from .bonus_reason import BUCKETS


class ProductBonusDispatch(models.Model):
    """The BO: a dispatcher, not a shipping record.

    This is his correction, and it matters. One act of marketing ("send A Casa
    do Sol to the press list") is ONE decision, but it becomes N shipments --
    each person has their own address, their own package to be made at the
    warehouse, and their own nota fiscal to be issued. Collapsing the two into a
    single document (as the first prototype did) means either the decision has
    no record, or the shipment has no address.

    So: BO/2026/00007 is the dispatch. It carries the choice, the quota, the
    approval and the campaign. It generates B00231, B00232, B00233... -- the
    fichas, which carry the address, the package and the note.

    It is also the unit that compares with paid media: "47 livros, R$ 580"
    against "um anúncio, R$ 4.000". A single B000 cannot make that argument.
    """
    _name = 'product.bonus.dispatch'
    _description = 'Bonus Dispatch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(default='/', copy=False, readonly=True, index=True)
    date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda s: s.env.company)

    product_id = fields.Many2one(
        'product.product', string="Title", required=True,
        domain=[('type', '=', 'consu')], tracking=True)
    reason_id = fields.Many2one(
        'product.bonus.reason', string="Reason", required=True, tracking=True)
    bucket = fields.Selection(related='reason_id.bucket', store=True, string="Investment")
    campaign = fields.Char(tracking=True, help="The launch, the fair, the push.")
    quantity = fields.Float(string="Copies each", default=1.0, required=True)
    user_id = fields.Many2one(
        'res.users', string="Responsible", default=lambda s: s.env.user, tracking=True)

    state = fields.Selection([
        ('draft', 'Triage'),
        ('approved', 'Approved'),
        ('sent', 'Sent'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)

    # The three sources ADD UP -- they are not a radio.
    #
    # "A lista de imprensa MAIS os jornalistas de SP que não estão nela MAIS o
    # Fulano que pediu" is one ordinary request, and forcing a single source
    # turned it into three dispatches, three approvals and three chances to
    # send the same person two books. Every source is a way of naming people;
    # naming them two ways at once is normal.
    #
    # Everything unions and dedups: somebody found by all three still gets ONE
    # book.
    list_ids = fields.Many2many(
        'product.bonus.list', string="VIP lists",
        help="The owners of these lists approve the dispatch -- once, not once "
             "per person. Somebody on two lists still gets a single copy.")
    category_id = fields.Many2many(
        'res.partner.category', string="Contact tags",
        help="Adds every contact carrying these tags. Empty adds nobody.")
    manual_partner_ids = fields.Many2many(
        'res.partner', string="Hand-picked",
        help="The author asked for one more. There is always one.")

    # A previous BO as a source -- and this one closes a loop.
    #
    # A dispatch already IS a curated selection: somebody sat down, looked at
    # the columns and decided these 47 people. "Send this to whoever got the
    # last book" is the most natural mailing base a publisher has, and it means
    # you almost never need to freeze a campaign into a permanent list. The BO
    # is already the record; now it is reusable.
    source_dispatch_ids = fields.Many2many(
        'product.bonus.dispatch', 'bonus_dispatch_source_rel', 'child_id', 'parent_id',
        string="Previous dispatches",
        domain="[('id', '!=', id), ('state', '!=', 'cancelled')]",
        help="Everyone who got a copy in these dispatches. The last launch is "
             "usually the best starting point for the next one.")

    line_ids = fields.One2many('product.bonus.dispatch.line', 'dispatch_id')
    bonus_ids = fields.One2many('product.bonus', 'dispatch_id')
    bonus_count = fields.Integer(compute='_compute_totals')
    total_cost = fields.Float(compute='_compute_totals')
    # The campaign's own return. "Pra que mandar se o fulano não recebeu ou fez
    # uma campanha meia boca" -- so after a BO ships, its evaluation has to be
    # right here, not buried one ficha at a time. It is also the payoff of the
    # media comparison: 47 books, R$ 580, and THIS is what came back.
    outcome_summary = fields.Char(
        compute='_compute_outcome', string="Avaliação")
    outcome_rate = fields.Char(compute='_compute_outcome', string="Avaliação")
    currency_id = fields.Many2one(related='company_id.currency_id')

    # --- the live counter -------------------------------------------------
    selected_count = fields.Integer(compute='_compute_counter')
    quota_allowed = fields.Float(compute='_compute_counter')
    quota_given = fields.Float(compute='_compute_counter')
    quota_left = fields.Float(compute='_compute_counter')
    quota_after = fields.Float(compute='_compute_counter')
    quota_pct = fields.Float(compute='_compute_counter')
    fits = fields.Boolean(compute='_compute_counter')
    counter_html = fields.Html(compute='_compute_counter', sanitize=False)
    print_run = fields.Float(compute='_compute_counter')
    sources_html = fields.Html(compute='_compute_sources', sanitize=False)
    checked = fields.Boolean(copy=False)
    check_html = fields.Html(sanitize=False, copy=False)

    _name_uniq = models.Constraint(
        'unique(name, company_id)', 'The dispatch number must be unique.')

    @api.depends('bonus_ids.total_cost')
    def _compute_totals(self):
        for rec in self:
            live = rec.bonus_ids.filtered(lambda b: b.state != 'cancelled')
            rec.bonus_count = len(live)
            rec.total_cost = sum(live.mapped('total_cost'))

    @api.depends('bonus_ids.outcome', 'bonus_ids.state')
    def _compute_outcome(self):
        labels = {'silence': "silêncio", 'weak': "meia-boca",
                  'good': "divulgou", 'great': "arrasou"}
        for rec in self:
            live = rec.bonus_ids.filtered(lambda b: b.state != 'cancelled')
            if not live:
                rec.outcome_summary = ""
                rec.outcome_rate = "—"
                continue
            parts = []
            lost = live.filtered(lambda b: b.state == 'lost')
            if lost:
                parts.append("%d não chegou" % len(lost))
            waiting = live.filtered(lambda b: b.is_waiting)
            if waiting:
                parts.append("%d aguardando" % len(waiting))
            for key, label in labels.items():
                n = len(live.filtered(lambda b: b.outcome == key))
                if n:
                    parts.append("%d %s" % (n, label))
            rec.outcome_summary = " · ".join(parts) or "—"
            judged = live.filtered(lambda b: b.outcome)
            ok = judged.filtered(lambda b: b.outcome in ('good', 'great'))
            rec.outcome_rate = (
                "%d de %d" % (len(ok), len(judged)) if judged else "—")

    @api.depends('line_ids.selected', 'product_id', 'reason_id', 'quantity')
    def _compute_counter(self):
        for rec in self:
            sel = rec.line_ids.filtered('selected')
            rec.selected_count = len(sel)
            asked = len(sel) * (rec.quantity or 0)
            quota = rec._quota()
            rec.quota_allowed = quota['allowed']
            rec.quota_given = quota['given']
            rec.quota_left = quota['left']
            rec.quota_pct = quota['pct']
            rec.print_run = quota['run']
            rec.quota_after = quota['left'] - asked
            # No print run means the meta is UNDEFINED, not zero. A book that
            # has not entered stock yet (the launch being planned right now)
            # must not block the press mailing -- blocking on an undefined meta
            # is the punishment pattern, and it fails towards "não mandou
            # livro", which is the other half of the problem.
            rec.fits = (not quota['run']) or (asked <= quota['left'])
            rec.counter_html = rec._render_counter(asked, quota)

    @api.depends('list_ids', 'category_id', 'manual_partner_ids',
                 'source_dispatch_ids', 'line_ids')
    def _compute_sources(self):
        """Show the arithmetic.

        Four sources that add up are only clear if you can see them adding. The
        dedup in particular is invisible work: "22 nomes, 7 repetidos, 15
        candidatos" is the difference between trusting the screen and counting
        by hand.
        """
        for rec in self:
            parts = []
            total = 0
            for lst in rec.list_ids:
                n = len(lst.member_ids.filtered('active'))
                total += n
                parts.append(('&#9679;', lst.name, n))
            for bo in rec.source_dispatch_ids:
                n = len(bo.bonus_ids.filtered(lambda b: b.state != 'cancelled'))
                total += n
                parts.append(('&#8635;', "%s (quem já recebeu)" % bo.name, n))
            filt = rec._filtered_partners()
            if filt:
                total += len(filt)
                label = ", ".join(rec.category_id.mapped('name'))
                parts.append(('&#9873;', "filtro: %s" % label, len(filt)))
            if rec.manual_partner_ids:
                total += len(rec.manual_partner_ids)
                parts.append(('&#9997;', "a dedo", len(rec.manual_partner_ids)))

            if not parts:
                rec.sources_html = (
                    '<div style="padding:8px 12px;color:#888;font-size:12px;">'
                    'Escolha de onde vem a gente. <b>As fontes somam</b> &mdash; '
                    'lista + disparo anterior + filtro + a dedo.</div>')
                continue
            unicos = len(rec._collect_partners())
            rows = ['<div style="padding:8px 12px;border:1px solid #eee;'
                    'border-radius:6px;background:#fcfcfc;font-size:12px;">']
            for icon, label, n in parts:
                rows.append('<div>%s %s &mdash; <b>%d</b></div>' % (icon, label, n))
            if len(parts) > 1:
                dup = total - unicos
                rows.append(
                    '<div style="margin-top:5px;padding-top:5px;'
                    'border-top:1px solid #eee;">'
                    '<b>%d</b> nomes somados &middot; <b>%d</b> repetidos &middot; '
                    '<b style="color:#28a745;">%d</b> candidatos' % (total, dup, unicos))
                if dup:
                    rows.append(' <span style="color:#888;">&mdash; quem aparece em '
                                'duas fontes recebe <b>um livro só</b></span>')
                rows.append('</div>')
            rows.append('</div>')
            rec.sources_html = ''.join(rows)

    def _quota(self):
        self.ensure_one()
        if not (self.product_id and self.reason_id):
            return {'allowed': 0, 'given': 0, 'left': 0, 'pct': 0, 'run': 0}
        return self.env['product.bonus.quota']._figures_for(
            self.product_id, self.reason_id.bucket, self.company_id)

    def _render_counter(self, asked, q):
        """The bar. The brake is a budget, not a permission: it has to be here,
        moving, while you choose -- not a "no" when you save."""
        self.ensure_one()
        if not self.product_id or not self.reason_id:
            return ('<div style="padding:8px 12px;border:1px solid #ddd;'
                    'border-radius:6px;background:#fafafa;color:#666;">'
                    'Escolha o t&iacute;tulo e o motivo.</div>')
        if not q['run']:
            # Say it plainly instead of showing "0 de 0", which reads as a meta
            # of zero when it is really a meta nobody can compute yet.
            return ('<div style="padding:10px 12px;border:1px solid #ddd;'
                    'border-radius:6px;background:#fafafa;color:#666;">'
                    '<b>Sem tiragem em estoque ainda</b> &mdash; a meta &eacute; '
                    '%.1f%% da tiragem, e ela s&oacute; existe quando o livro '
                    'entra. At&eacute; l&aacute; nada trava.</div>' % q['pct'])
        allowed = q['allowed'] or 1
        used_pct = min(100.0, (q['given'] / allowed) * 100.0)
        asked_pct = min(100.0 - used_pct, (asked / allowed) * 100.0)
        colour = '#28a745' if self.fits else '#dc3545'
        left = q['left'] - asked
        if self.fits:
            msg = ('<b>%d</b> selecionados &middot; cabe na meta &check; '
                   '&middot; sobram <b>%d</b>' % (self.selected_count, max(0, left)))
        else:
            msg = ('<b style="color:#dc3545;">Estoura a meta em %d exemplares.</b> '
                   'Um gestor pode liberar, e a libera&ccedil;&atilde;o fica registrada.'
                   % abs(left))
        nudge = ''
        if self.fits and left > 0 and self.selected_count:
            # Meta nao gasta e pendencia, nao economia.
            nudge = ('<div style="margin-top:4px;color:#888;font-size:11px;">'
                     'Meta n&atilde;o gasta &eacute; pend&ecirc;ncia, n&atilde;o '
                     'economia &mdash; ainda cabem %d.</div>' % int(left))
        return (
            '<div style="padding:10px 12px;border:1px solid #ddd;border-radius:6px;'
            'background:#fff;">'
            '<div style="font-size:11px;color:#888;text-transform:uppercase;'
            'letter-spacing:.5px;">Meta &middot; %s &middot; %s</div>'
            '<div style="height:14px;background:#eee;border-radius:7px;'
            'overflow:hidden;margin:6px 0;">'
            '<div style="height:100%%;width:%.1f%%;background:#6c757d;float:left;"></div>'
            '<div style="height:100%%;width:%.1f%%;background:%s;float:left;"></div>'
            '</div>'
            '<div style="font-size:13px;">%s</div>'
            '<div style="font-size:11px;color:#888;margin-top:3px;">'
            'j&aacute; doados %d de %d &middot; tiragem %d &middot; meta %.1f%% da tiragem'
            '</div>%s</div>'
        ) % (
            dict(BUCKETS).get(self.bucket, ''), self.product_id.display_name or '',
            used_pct, asked_pct, colour, msg,
            int(q['given']), int(q['allowed']), int(q['run']), q['pct'], nudge,
        )

    # --- loading ----------------------------------------------------------
    @api.onchange('list_ids', 'category_id',
                  'manual_partner_ids', 'source_dispatch_ids', 'product_id')
    def _onchange_source(self):
        if not self.product_id:
            return
        partners = self._collect_partners()
        self.line_ids = [(5, 0, 0)] + [
            (0, 0, self._prepare_line(p)) for p in partners]

    def _collect_partners(self):
        """The union of every source. The ORM dedups: one person, one book."""
        self.ensure_one()
        out = self.env['res.partner']
        for lst in self.list_ids:
            out |= lst.member_ids.filtered('active').mapped('partner_id')
        out |= self._filtered_partners()
        out |= self.manual_partner_ids
        for bo in self.source_dispatch_ids:
            out |= bo.bonus_ids.filtered(
                lambda b: b.state != 'cancelled').mapped('partner_id')
        return out

    def _filtered_partners(self):
        """The ad-hoc filter. Empty adds NOBODY.

        The old version fell back to "every bonus recipient" when no criteria
        were set, which was a booby trap: with the sources adding up, an empty
        filter would quietly pour the whole address book on top of your list.
        Silence must add nothing.
        """
        self.ensure_one()
        if not self.category_id:
            return self.env['res.partner']
        return self.env['res.partner'].search([
            ('is_company', '=', False),
            ('category_id', 'in', self.category_id.ids),
        ], limit=300)

    def _prepare_line(self, partner):
        """Only `selected` is decided here -- the columns compute themselves."""
        self.ensure_one()
        has_title = bool(self.env['product.bonus'].search_count([
            ('partner_id', '=', partner.id),
            ('state', '!=', 'cancelled'),
            ('line_ids.product_id', '=', self.product_id.id),
        ]))
        return {'partner_id': partner.id, 'selected': not has_title}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'product.bonus.dispatch') or '/'
        return super().create(vals_list)

    def action_reload(self):
        self.ensure_one()
        self._onchange_source()
        return True

    def action_select_all(self):
        self.line_ids.filtered(lambda l: not l.has_title).selected = True
        return True

    def action_select_none(self):
        self.line_ids.selected = False
        return True

    def action_save_as_list(self):
        """The output becomes the input: a good triage deserves to last."""
        self.ensure_one()
        sel = self.line_ids.filtered('selected')
        if not sel:
            raise UserError(_("Nothing selected."))
        new = self.env['product.bonus.list'].create({
            'name': self.campaign or self.product_id.display_name,
            'member_ids': [(0, 0, {'partner_id': l.partner_id.id}) for l in sel],
        })
        return {'type': 'ir.actions.act_window', 'res_model': 'product.bonus.list',
                'res_id': new.id, 'view_mode': 'form'}

    def action_check(self):
        """"Can we actually send?" -- a list of what is crooked, with the fix
        next to it. Never a pop-up error: a "no" without a fix loses a user."""
        self.ensure_one()
        sel = self.line_ids.filtered('selected')
        if not sel:
            raise UserError(_("Nothing selected."))
        no_address = sel.filtered(lambda l: not l.address_ok)
        dup = sel.filtered('has_title')
        ready = sel - no_address - dup
        asked = len(sel) * self.quantity
        rows = ['<div style="font-size:14px;line-height:1.9;">',
                '<div>&check; <b>%d</b> prontas</div>' % len(ready)]
        if no_address:
            rows.append('<div style="color:#b8860b;">&#9888; <b>%d</b> sem endere&ccedil;o'
                        ' &mdash; sem CEP n&atilde;o sai etiqueta: %s</div>'
                        % (len(no_address), ', '.join(
                            no_address[:5].mapped('partner_id.display_name'))))
        if dup:
            rows.append('<div style="color:#b8860b;">&#9888; <b>%d</b> j&aacute; recebeu '
                        'este t&iacute;tulo: %s</div>' % (len(dup), ', '.join(
                            dup[:5].mapped('partner_id.display_name'))))
        rows.append('<div>%s Meta &middot; %d de %d &middot; sobram %d</div>'
                    % ('&check;' if self.fits else '&#9888;',
                       int(self.quota_given + asked), int(self.quota_allowed),
                       int(max(0, self.quota_after))))
        avail = self.product_id.qty_available
        rows.append('<div>%s Estoque &middot; %d de %d dispon&iacute;veis</div>'
                    % ('&check;' if avail >= asked else '&#9888;', int(asked), int(avail)))
        rows.append('<div>&check; Custo &middot; R$ %.2f &mdash; '
                    '<i>quanto custaria o an&uacute;ncio equivalente?</i></div>'
                    % (asked * (self.product_id.standard_price or 0)))
        rows.append('</div>')
        self.write({'check_html': ''.join(rows), 'checked': True})
        return True

    def action_approve(self):
        """Approved ONCE, here -- not 47 times, one per person."""
        for rec in self:
            if rec.state != 'draft':
                continue
            rec._generate_bonuses()
            rec.state = 'approved'
            rec.bonus_ids.filtered(lambda b: b.state == 'draft').action_approve()
        return True

    def _generate_bonuses(self):
        """One B000 per person (D7): each has an address, a package to be made
        at the warehouse, and a nota fiscal to be issued."""
        self.ensure_one()
        sel = self.line_ids.filtered(lambda l: l.selected and l.address_ok)
        if not sel:
            raise UserError(_(
                "Nothing to send: everything selected is without an address."))
        if not self.fits and not self.env.user.has_group(
                'liber_product_bonus.group_bonus_manager'):
            raise UserError(_("Over quota. A manager can release it."))
        self.bonus_ids.filtered(lambda b: b.state == 'draft').unlink()
        for line in sel:
            self.env['product.bonus'].create({
                'dispatch_id': self.id,
                'partner_id': line.partner_id.id,
                'reason_id': self.reason_id.id,
                'list_id': self._list_for(line.partner_id),
                'campaign': self.campaign,
                'date': self.date,
                'line_ids': [(0, 0, {
                    'product_id': self.product_id.id,
                    'quantity': self.quantity,
                    'unit_cost': self.product_id.standard_price,
                })],
            })

    def _list_for(self, partner):
        """Which list to credit this ficha to.

        Somebody on two lists gets one book, so the cost has to land on one of
        them -- the first match. It is an arbitrary tie-break and it is worth
        knowing about: "gasto por lista" under-counts a shared name for the
        second list. The alternative (splitting a book in half across two lists)
        would be worse and fake.
        """
        self.ensure_one()
        for lst in self.list_ids:
            if partner in lst.member_ids.filtered('active').mapped('partner_id'):
                return lst.id
        return False

    def action_send_all(self):
        for rec in self:
            todo = rec.bonus_ids.filtered(lambda b: b.state in ('draft', 'approved'))
            todo.action_send()
            rec.state = 'sent'
        return True

    def action_cancel(self):
        self.bonus_ids.filtered(
            lambda b: b.state in ('draft', 'approved')).action_cancel()
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'draft', 'checked': False})

    def action_view_bonuses(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _("Bonificações"),
            'res_model': 'product.bonus',
            'domain': [('dispatch_id', '=', self.id)],
        }
        # One ficha -> open it directly, so the breadcrumb reads its number
        # (B00187) instead of a generic "Bonificações" list.
        if len(self.bonus_ids) == 1:
            action.update(view_mode='form', res_id=self.bonus_ids.id)
        else:
            action['view_mode'] = 'list,form'
        return action


class ProductBonusDispatchLine(models.Model):
    """A candidate in the triage. Not a shipment yet -- a row you say yes or no
    to."""
    _name = 'product.bonus.dispatch.line'
    _description = 'Bonus Dispatch Candidate'
    # Ordered by id: the decision columns are computed, and a non-stored field
    # cannot be an ORDER BY.
    _order = 'id'

    dispatch_id = fields.Many2one(
        'product.bonus.dispatch', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', required=True)
    selected = fields.Boolean(
        help="Marque quem recebe. É o 'vai ou não vai?' desta linha.")

    # Computed from the partner, never written by the onchange: a field the
    # client treats as read-only is not sent back, and the columns that ARE the
    # decision would arrive blank. A triage showing everyone as "0" is worse
    # than no triage -- it looks like an answer.
    has_title = fields.Boolean(
        compute='_compute_stats', string="Already has it",
        help="Esta pessoa já recebeu ESTE título antes.")
    received_count = fields.Integer(compute='_compute_stats', string="Received")
    outcome_rate = fields.Char(compute='_compute_stats', string="Return")
    # "0 de 22" e "1 de 1" tinham o mesmo peso visual e significam o oposto.
    # A nota separa os dois; a fração vira detalhe na dica.
    rating_label = fields.Char(compute='_compute_stats', string="Score",
                               help=SCORE_HELP)
    rating_html = fields.Html(compute='_compute_stats', string="Score",
                              sanitize=False, help=SCORE_HELP)
    rating_band = fields.Selection(
        related='partner_id.bonus_rating_band', string="Situação")
    partner_bio = fields.Char(
        related='partner_id.bonus_bio', string="Who they are")
    partner_type = fields.Selection(
        related='partner_id.bonus_partner_type', string="Partner type")
    last_date = fields.Date(compute='_compute_stats', string="Last")
    address_ok = fields.Boolean(
        compute='_compute_stats', string="Address",
        help="Tem endereço utilizável: rua, CEP e cidade. Sem isto o pacote "
             "não sai do depósito.")
    # No phone here: on the triage you are choosing, not calling. The phone
    # belongs on the follow-up report, where the task IS to call and ask whether
    # the book arrived.
    # With four sources adding up, "why is this person here?" stops being
    # obvious -- and it is the first thing you ask when a name surprises you.
    origin = fields.Char(compute='_compute_origin', string="Came from")

    @api.depends('partner_id', 'dispatch_id.product_id')
    def _compute_stats(self):
        for line in self:
            partner = line.partner_id
            product = line.dispatch_id.product_id
            if not partner:
                line.has_title = False
                line.received_count = 0
                line.outcome_rate = "—"
                line.rating_label = ""
                line.rating_html = ""
                line.last_date = False
                line.address_ok = False
                continue
            live = self.env['product.bonus'].search([
                ('partner_id', '=', partner.id), ('state', '!=', 'cancelled')])
            same = live.filtered(
                lambda b: product and product in b.line_ids.mapped('product_id'))
            judged = live.filtered(lambda b: b.outcome)
            ok = judged.filtered(lambda b: b.outcome in ('good', 'great'))
            line.has_title = bool(same)
            line.received_count = len(live)
            # "—", never "0 of 0": no history is an invitation, not a demerit.
            line.outcome_rate = (
                "%d de %d" % (len(ok), len(judged)) if judged else "—")
            Rating = self.env['bonus.rating.mixin']
            score, label, _trend, n = Rating._rating_for(live)
            line.rating_label = label
            line.rating_html = Rating._rating_html(
                label, partner.bonus_rating_band, n,
                Rating._rating_settings()[1])
            line.last_date = max(live.mapped('date'), default=False)
            line.address_ok = bool(partner.street and partner.zip and partner.city)

    @api.depends('partner_id', 'dispatch_id.list_ids',
                 'dispatch_id.manual_partner_ids', 'dispatch_id.source_dispatch_ids')
    def _compute_origin(self):
        for line in self:
            d, p = line.dispatch_id, line.partner_id
            if not (d and p):
                line.origin = ''
                continue
            src = []
            for lst in d.list_ids:
                if p in lst.member_ids.filtered('active').mapped('partner_id'):
                    src.append(lst.name)
            for bo in d.source_dispatch_ids:
                if p in bo.bonus_ids.mapped('partner_id'):
                    src.append(bo.name)
            if p in d.manual_partner_ids:
                src.append("a dedo")
            if p in d._filtered_partners():
                src.append("filtro")
            line.origin = " + ".join(src) if src else ""
