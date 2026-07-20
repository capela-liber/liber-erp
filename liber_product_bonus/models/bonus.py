# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .bonus_reason import BUCKETS

# His words, on purpose. A scale named in corridor language gets filled in;
# "Level 2 -- Partial Engagement" does not.
OUTCOMES = [
    ('silence', 'Silence'),
    ('weak', 'Half-hearted'),
    ('good', 'Covered it'),
    ('great', 'Nailed it'),
]
# Which outcomes count as "it worked" for the raw rate ("5 of 7").
OUTCOME_OK = ('good', 'great')


class ProductBonus(models.Model):
    _name = 'product.bonus'
    _description = 'Bonus Copy'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(default='/', copy=False, readonly=True, index=True)
    # The ficha. BO/2026/00007 is the dispatch that ordered it; B00231 is this
    # package, with this address and this nota fiscal.
    dispatch_id = fields.Many2one(
        'product.bonus.dispatch', string="Dispatch", ondelete='set null',
        index=True, readonly=True)
    date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda s: s.env.company)

    partner_id = fields.Many2one(
        'res.partner', string="Recipient", required=True, tracking=True,
        index=True, ondelete='restrict')
    reason_id = fields.Many2one(
        'product.bonus.reason', string="Reason", required=True, tracking=True,
        ondelete='restrict')
    # "Investimento": qual verba paga (editorial/marketing/comercial).
    bucket = fields.Selection(
        related='reason_id.bucket', store=True, readonly=True, string="Investment")
    # "Tipo de parceiro": quem recebe. Stored para virar dimensão de pivot.
    partner_type = fields.Selection(
        related='partner_id.bonus_partner_type', store=True, string="Partner type")
    list_id = fields.Many2one(
        'product.bonus.list', string="VIP list", ondelete='set null', index=True,
        help="Which list this came from. The list's owner approves it.")
    campaign = fields.Char(help="Free text: the launch, the fair, the push.")
    # Only on the follow-up report, not one click away there: that screen's
    # whole task is to CALL and ask whether the book arrived, and opening the
    # contact to find the number is the friction that makes the call not happen.
    # It is deliberately absent from the triage, where you are choosing.
    phone = fields.Char(related='partner_id.phone', string="Phone")
    user_id = fields.Many2one(
        'res.users', string="Responsible", default=lambda s: s.env.user, tracking=True)

    line_ids = fields.One2many('product.bonus.line', 'bonus_id')

    # ------------------------------------------------------------------
    # The ladder.  draft -> approved -> sent -> arrived -> closed
    #                                       \-> lost -> (resend)
    # "Arrived?" is a state and not a flag (U3): it gives filters, a graph and
    # the face of a closed loop.
    # ------------------------------------------------------------------
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('sent', 'Sent'),
        ('arrived', 'Arrived'),
        ('lost', 'Never arrived'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)

    # ------------------------------------------------------------------
    # The B000 is homologous to the consignment C000/S000: a document that
    # COORDINATES logistics and the note. It does not EMIT the note -- the repo
    # is import-only, like consignment -- it ties the MOV to the fiscal note and
    # tracks the note through its lifecycle, and it doubles as the artifact for
    # talking to the author (arrived? / how did it go?).
    #
    #   1) Logística  -> picking_id     (MOV, BON/)
    #   2) Nota       -> note_move_id   (the REM/ remessa note, never paid)
    #   3) NF-e (XML) -> nfe_xml_panel_id / nfe_key / fiscal_state
    #   4) Comunicação-> arrived/outcome (further down)
    # ------------------------------------------------------------------

    # 1) Logistics: the MOV. Its own operation type (BON/), never the
    # warehouse's generic Delivery Orders -- a bonus among the deliveries reads
    # as a sale somebody forgot to invoice.
    picking_id = fields.Many2one(
        'stock.picking', string="Shipment", readonly=True, copy=False)
    picking_state = fields.Selection(related='picking_id.state', string="MOV")

    # 2) The remessa note (REM/): a real invoice document in the remessa
    # journal, auto-settled on post so it NEVER generates payment. Same engine
    # as every other note in the house (nfe_remessa), prepared for the future
    # NF-e emission -- nothing bonus-specific about its shape.
    note_move_id = fields.Many2one(
        'account.move', string="Remessa note", readonly=True, copy=False)
    note_state = fields.Selection(related='note_move_id.state', string="Note status")
    # The stat button used to vanish when there was no entry yet -- so on an
    # approved B000 (the common case) the form answered "where is the note?"
    # with silence. It answers "A emitir" now: absent is a state, not nothing.
    note_label = fields.Char(compute='_compute_note_label', string="Note")

    @api.depends('note_move_id.name')
    def _compute_note_label(self):
        # "nota lançado faz sentido? 'nota' já seria bom, pois ela só pode
        # estar lançada." O estado era redundante; o NÚMERO não é -- ele liga
        # o botão à lista de Remessas. Antes de existir, "A emitir".
        for rec in self:
            rec.note_label = rec.note_move_id.name or "A emitir"

    # 3) The fiscal note -- the NF-e itself (remessa em bonificação, CFOP 5910).
    # Emitted OUTSIDE (nfe_xml is import-only; the house's XML solution is being
    # designed separately -- nothing here anticipates it) and
    # matched back by nfe_key, exactly like consignment matches its notes. The
    # B000 coordinates it; it never emits it.
    cfop_id = fields.Many2one(
        'nfe.cfop', string="CFOP", readonly=True, copy=False,
        help="Remessa em bonificação (5910/6910). Stamped for the NF-e.")
    nfe_key = fields.Char(
        string="NF-e key", size=44, copy=False, index='btree_not_null',
        help="44-digit access key of the remessa NF-e, once emitted and "
             "imported. This key -- not an id -- ties the B000 to its note.")
    nfe_xml_panel_id = fields.Many2one(
        'nfe.xml.panel', string="NF-e", compute='_compute_nfe_panel',
        inverse='_inverse_nfe_panel', store=True, copy=False,
        help="The imported NF-e panel, resolved by the access key.")
    fiscal_state = fields.Selection([
        ('to_emit', 'To emit'),
        ('emitted', 'Emitted'),
        ('reconciled', 'Reconciled'),
    ], compute='_compute_fiscal_state', store=True, string="Note status")

    sent_date = fields.Date(readonly=True, copy=False)
    arrived_date = fields.Date(readonly=True, copy=False)

    # When to call and ask "chegou?". The real arrival date needs a proper
    # estimate (distance, carrier) -- for now it is a configurable X days after
    # release (Definições > Bonificações). After that, the ficha shows up on the
    # "Retorno" list with the phone, so somebody calls.
    call_date = fields.Date(
        compute='_compute_call', string="Call on",
        help="When to call the recipient to confirm arrival.")
    to_call = fields.Boolean(
        compute='_compute_call', search='_search_to_call', string="To call")
    tracking_ref = fields.Char(string="Tracking code")

    # --- the return: the other half of the module's reason to exist --------
    outcome = fields.Selection(OUTCOMES, tracking=True, copy=False, index=True)
    # A situação do parceiro NO MOMENTO DO ENVIO, congelada. Sem isto o
    # relatório mentiria: hoje a pessoa é "Sem retorno" PORQUE mandamos, e
    # cruzar custo com a situação de hoje leria como se soubéssemos antes.
    # Congelado, dá para perguntar "quanto apostamos em quem já estava frio?".
    partner_band_at_send = fields.Selection(
        [('new', "Novo"), ('testing', "Em teste"), ('cold', "Sem retorno"),
         ('fading', "Esfriando"), ('steady', "Constante"), ('warm', "Rendendo")],
        string="Situação no envio", readonly=True, copy=False, index=True)
    outcome_link = fields.Char(
        string="Link",
        help="The post, the review, the video. 'Covered it' without a link is "
             "an opinion; with a link it is a fact -- and in two years someone "
             "can click it instead of trusting the memory of a person who has "
             "left the company.")
    outcome_date = fields.Date(readonly=True, copy=False)
    outcome_user_id = fields.Many2one('res.users', readonly=True, copy=False)

    deadline = fields.Date(
        compute='_compute_deadline', store=True,
        help="When the return window closes. Until then it is 'waiting', "
             "not 'silence'.")
    is_waiting = fields.Boolean(compute='_compute_is_waiting', search='_search_is_waiting')

    total_cost = fields.Float(compute='_compute_total_cost', store=True)
    quantity = fields.Float(compute='_compute_total_cost', store=True)
    # A ficha é sempre um título (D7: 1 B000 por pessoa). Stored para virar
    # dimensão de relatório sem precisar joinar as linhas.
    product_id = fields.Many2one(
        'product.product', compute='_compute_total_cost', store=True, string="Title")
    currency_id = fields.Many2one(related='company_id.currency_id')

    _name_uniq = models.Constraint(
        'unique(name, company_id)',
        'The bonus number must be unique.',
    )

    @api.depends('line_ids.quantity', 'line_ids.unit_cost', 'line_ids.product_id')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = sum(l.quantity * l.unit_cost for l in rec.line_ids)
            rec.quantity = sum(rec.line_ids.mapped('quantity'))
            rec.product_id = rec.line_ids[:1].product_id

    def _days_to_call(self):
        try:
            return int(self.env['ir.config_parameter'].sudo().get_param(
                'product_bonus.days_to_call', 10))
        except (TypeError, ValueError):
            return 10

    @api.depends('sent_date', 'state')
    def _compute_call(self):
        # Not stored on purpose: it reads the config each time, so changing "X
        # days" in Settings takes effect without a recompute cron.
        days = self._days_to_call()
        today = fields.Date.context_today(self)
        for rec in self:
            rec.call_date = (
                rec.sent_date + relativedelta(days=days) if rec.sent_date else False)
            rec.to_call = bool(
                rec.state == 'sent' and rec.call_date and rec.call_date <= today)

    def _search_to_call(self, operator, value):
        cutoff = fields.Date.context_today(self) - relativedelta(days=self._days_to_call())
        # v19 normalizes ('to_call','=',True) to operator='in', value={True}.
        if operator == 'in':
            want_true = True in value
        elif operator == 'not in':
            want_true = True not in value
        elif operator == '=':
            want_true = bool(value)
        else:  # '!='
            want_true = not bool(value)
        if want_true:
            return [('state', '=', 'sent'), ('sent_date', '!=', False),
                    ('sent_date', '<=', cutoff)]
        return ['|', '|', ('state', '!=', 'sent'), ('sent_date', '=', False),
                ('sent_date', '>', cutoff)]

    @api.depends('nfe_key')
    def _compute_nfe_panel(self):
        # Resolved through the key, like the account.move in nfe_xml: the link
        # survives exports and restores and rebuilds from the documents.
        Panel = self.env['nfe.xml.panel']
        for rec in self:
            if rec.nfe_key:
                rec.nfe_xml_panel_id = Panel.search(
                    [('key', '=', rec.nfe_key)], limit=1)
            # else keep whatever was set manually

    def _inverse_nfe_panel(self):
        for rec in self:
            if rec.nfe_xml_panel_id.key:
                rec.nfe_key = rec.nfe_xml_panel_id.key

    @api.depends('nfe_key', 'nfe_xml_panel_id', 'note_move_id.nfe_key')
    def _compute_fiscal_state(self):
        """The note lifecycle the B000 coordinates -- it does not emit.

        A emitir  -> the movement happened, the NF-e does not exist yet (it is
                     emitted outside and imported, like consignment).
        Emitida   -> the NF-e is in (key present / panel matched).
        Conciliada-> the NF-e is also tied to the accounting entry.
        """
        for rec in self:
            has_note = bool(rec.nfe_key or rec.nfe_xml_panel_id)
            reconciled = bool(
                has_note and rec.note_move_id.nfe_key
                and rec.note_move_id.nfe_key == rec.nfe_key)
            rec.fiscal_state = (
                'reconciled' if reconciled else 'emitted' if has_note else 'to_emit')

    @api.depends('sent_date', 'reason_id.return_window_days')
    def _compute_deadline(self):
        for rec in self:
            if rec.sent_date and rec.reason_id:
                rec.deadline = rec.sent_date + relativedelta(
                    days=rec.reason_id.return_window_days or 0)
            else:
                rec.deadline = False

    def _compute_is_waiting(self):
        # Waiting != silence. Someone who got the book yesterday cannot show up
        # as a failure today; the state ages on its own when the window closes.
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_waiting = bool(
                rec.state in ('sent', 'arrived')
                and not rec.outcome
                and rec.deadline and rec.deadline >= today)

    def _search_is_waiting(self, operator, value):
        today = fields.Date.context_today(self)
        dom = [('state', 'in', ('sent', 'arrived')), ('outcome', '=', False),
               ('deadline', '>=', today)]
        if (operator == '=' and not value) or (operator == '!=' and value):
            return ['!'] + dom
        return dom

    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'product.bonus') or '/'
        return super().create(vals_list)

    def action_approve(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            # Author copies skip approval: the contract approved them when it
            # was signed. Asking again is theatre.
            rec.state = 'approved'
            if not rec.reason_id.requires_approval:
                rec.message_post(body=_(
                    "Approved automatically: reason %s does not require it "
                    "(the contract already did).", rec.reason_id.name))
        return True

    def action_send(self):
        for rec in self:
            if rec.state not in ('draft', 'approved'):
                raise UserError(_("%s is not ready to be sent.", rec.name))
            if rec.reason_id.requires_approval and rec.state == 'draft':
                raise UserError(_(
                    "%(name)s needs approval first (reason: %(reason)s).",
                    name=rec.name, reason=rec.reason_id.name))
            rec._check_quota()
            rec._freeze_cost()
            rec._create_picking()
            # The note is NOT generated here -- it is an explicit step, like the
            # S000: "Gerar nota". Sending only releases to logistics.
            rec.write({
                'state': 'sent',
                'sent_date': fields.Date.context_today(rec),
                'partner_band_at_send': rec.partner_id.bonus_rating_band,
            })
            # A lista acompanha: "Último envio" existe para dizer quais listas
            # esfriaram, e um campo que só o import escrevia mentia a partir do
            # primeiro envio de verdade. Só para frente, como no import.
            blist = rec.list_id
            if blist and (not blist.last_shipment_on
                          or rec.sent_date > blist.last_shipment_on):
                blist.last_shipment_on = rec.sent_date
        return True

    def action_generate_note(self):
        """Generate the fiscal note -- like any S000.

        The note is a nota de simples remessa (CFOP 5910), and it has to be
        MAPPED: the CFOP and the accounts must be configured in Definições >
        Bonificações. Without the mapping there is no note to generate, and we
        say exactly what is missing instead of booking something half-defined.
        """
        for rec in self:
            if rec.state not in ('sent', 'arrived', 'closed'):
                raise UserError(_(
                    "%s: send it to logistics first, then generate the note.",
                    rec.name))
            if rec.note_move_id:
                continue
            company = rec.company_id
            if not company.bonus_cfop_id:
                raise UserError(_(
                    "The bonus note is a nota de simples remessa (CFOP 5910) and "
                    "it must be mapped. Set the CFOP in Definições > Bonificações."))
            if not company._bonus_fiscal_ready():
                raise UserError(_(
                    "The bonus fiscal position is not mapped (it needs Auto "
                    "Invoice Paid and its account). Set it in Definições > "
                    "Bonificações before generating the note."))
            rec._create_remessa_note()
        return True

    def _create_remessa_note(self):
        """Create the remessa note -- a real invoice that never asks payment.

        This replaces the old account.move type 'entry': he could not find that
        one ("poderia me apontar onde está a nota aqui?"), and he was right --
        a journal entry is not a note. The note now is an out_invoice in the
        REM/ journal (nfe_remessa): invoice form, fiscal position, product
        lines at commercial value, its own sequence, listed in Faturamento >
        Remessas with every other movement note -- and auto-settled on post,
        so nothing is ever owed. Tomorrow the XML solution reads a standard
        invoice; nothing here anticipates it beyond existing.

        The analytic cost stays on the B000 lines (unit_cost): the nota goes
        out at commercial value, the budget burns cost. Two numbers, two
        homes, neither becomes the other.
        """
        self.ensure_one()
        if self.note_move_id:
            return self.note_move_id
        company = self.company_id
        # Stamp the CFOP regardless -- it classifies the movement (remessa em
        # bonificação) even before there is an XML.
        if company.bonus_cfop_id and not self.cfop_id:
            self.cfop_id = company.bonus_cfop_id
        note = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'journal_id': company._get_remessa_journal().id,
            'partner_id': self.partner_id.id,
            'fiscal_position_id': company.bonus_fiscal_position_id.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_origin': self.name,
            'bonus_id': self.id,
            'remessa_origin': 'bonus',
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                })
                for line in self.line_ids
            ],
        })
        note.action_post()
        self.note_move_id = note
        return note

    def action_view_note(self):
        self.ensure_one()
        if not self.note_move_id:
            raise UserError(_(
                "Esta bonificação ainda não tem nota.\n\n"
                "A nota é gerada pelo botão \"Gerar nota\" no topo, depois que a "
                "bonificação é enviada para a logística."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.note_move_id.id,
            'view_mode': 'form',
        }

    def action_reconcile_nfe(self):
        """Tie the emitted NF-e to the accounting entry.

        The B000 coordinates -- it does not emit. When the remessa NF-e comes
        back (nfe_key set, imported panel matched), stamp the same key on the
        expense entry so the two are one document. That is 'Conciliada'.
        """
        for rec in self:
            if not rec.nfe_key:
                raise UserError(_(
                    "%s has no NF-e key yet -- the note has not been emitted.",
                    rec.name))
            if rec.note_move_id and not rec.note_move_id.nfe_key:
                rec.note_move_id.nfe_key = rec.nfe_key
            rec.message_post(body=_("NF-e %s reconciled with the entry.", rec.nfe_key))
        return True

    def action_view_nfe(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'nfe.xml.panel',
            'res_id': self.nfe_xml_panel_id.id,
            'view_mode': 'form',
        }

    def _create_picking(self):
        """Release the shipment to logistics -- do NOT complete it.

        A comp copy is a real shipment out the door, so the BON/ picking cannot
        be marked done automatically: it has to be EXPEDITED -- physically
        picked, packed and shipped by the warehouse. So this only creates,
        confirms and reserves it; the warehouse validates it later through the
        Stock app, exactly like consignment.move.action_release.

        Until then the book has NOT left: it is reserved, not gone. The B000's
        MOV stat button shows the picking state (Reservado -> Concluído) so
        nobody mistakes 'released' for 'shipped'.

        Never writes stock.quant directly (invariant of the repo): every
        physical movement goes through a picking.
        """
        self.ensure_one()
        if self.picking_id:
            return self.picking_id
        ptype = self.company_id._get_bonus_operation_type()
        if not ptype:
            raise UserError(_(
                "No warehouse on %s: the book cannot leave.", self.company_id.name))
        picking = self.env['stock.picking'].create({
            'picking_type_id': ptype.id,
            'partner_id': self.partner_id.id,
            'origin': self.name,
            'location_id': ptype.default_location_src_id.id,
            'location_dest_id': ptype.default_location_dest_id.id,
            'company_id': self.company_id.id,
            'move_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'location_id': ptype.default_location_src_id.id,
                'location_dest_id': ptype.default_location_dest_id.id,
                'company_id': self.company_id.id,
            }) for line in self.line_ids],
        })
        # Confirm and reserve, then stop. NO button_validate: the warehouse
        # expedites. Leaving it here (assigned/waiting) is the point -- the book
        # has not shipped yet.
        picking.action_confirm()
        picking.action_assign()
        self.picking_id = picking
        return picking

    def action_view_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
        }

    def action_arrived(self):
        # Bulk-safe: works for one (the header button) or many (the "Confirmar
        # chegada" action on the list, after a batch of calls). Only sent ones
        # move -- a mixed selection does not drag drafts into 'arrived'.
        todo = self.filtered(lambda b: b.state == 'sent')
        todo.write({'state': 'arrived',
                    'arrived_date': fields.Date.context_today(self)})
        return True

    def action_lost(self):
        # Not the recipient's fault. The post office lost it. Punishing the
        # journalist for that is exactly backwards -- so this offers a resend
        # and never touches their record.
        for rec in self:
            rec.state = 'lost'
            rec.message_post(body=_(
                "Never arrived. This is a logistics failure, not a return "
                "failure -- it does not count against %s.", rec.partner_id.display_name))
        return True

    def action_resend(self):
        """A fresh B000, same recipient, same title. The lost one stays lost."""
        new = self.env['product.bonus']
        for rec in self:
            copy = rec.copy({
                'campaign': rec.campaign,
                'date': fields.Date.context_today(rec),
            })
            copy.message_post(body=_("Resent after %s never arrived.", rec.name))
            new |= copy
        if len(new) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'product.bonus',
                'res_id': new.id,
                'view_mode': 'form',
            }
        return True

    def action_view_partner_history(self):
        """Open everything this recipient ever got. The history is the point."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Bonificações — %s", self.partner_id.display_name),
            'res_model': 'product.bonus',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.partner_id.id)],
        }

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset(self):
        self.write({'state': 'draft'})

    # --- the outcome: one click, from wherever you already are -------------
    def _set_outcome(self, value):
        self.write({'outcome': value})
        return True

    def write(self, vals):
        """Quem carimba a avaliação é o CAMPO, não o botão.

        Antes, data/autor/encerramento saíam de _set_outcome -- então avaliar
        pela statusbar (ou por importação, ou pela API) gravava o resultado sem
        dizer quando nem por quem. O carimbo pertence à mudança do campo.
        """
        if vals.get('outcome'):
            vals = dict(vals)
            vals.setdefault('outcome_date', fields.Date.context_today(self))
            vals.setdefault('outcome_user_id', self.env.user.id)
            vals.setdefault('state', 'closed')
        return super().write(vals)

    def action_outcome_silence(self):
        return self._set_outcome('silence')

    def action_outcome_weak(self):
        return self._set_outcome('weak')

    def action_outcome_good(self):
        return self._set_outcome('good')

    def action_outcome_great(self):
        return self._set_outcome('great')

    # ------------------------------------------------------------------
    def _check_quota(self):
        """The hard block. It is the net, not the method (UX.md sec.2).

        If the UX works almost nobody reaches this: the live counter on the
        triage screen tells people while they choose, not when they save.
        """
        self.ensure_one()
        Quota = self.env['product.bonus.quota']
        for line in self.line_ids:
            # Same source as the live counter on the dispatch bar, so the number
            # that guides and the number that blocks can never disagree.
            quota = Quota._figures_for(line.product_id, self.bucket, self.company_id)
            if not quota['run']:
                continue
            if self.env.context.get('bonus_force_quota'):
                self.message_post(body=_(
                    "Quota override for %(product)s by %(user)s.",
                    product=line.product_id.display_name,
                    user=self.env.user.display_name))
                continue
            if line.quantity > quota['left']:
                # The message IS the design: a block that only says "no" is the
                # punishment we are trying to avoid. It has to say how much is
                # left and who can release it -- dict(BUCKETS), not
                # self._fields['bucket'].selection, which on a related field is
                # a callable and blows up right here, replacing the explanation
                # with a traceback.
                raise UserError(_(
                    "Over quota for %(product)s (%(bucket)s).\n\n"
                    "Allowed %(allowed)s, already given %(given)s, "
                    "left %(left)s -- this asks for %(asked)s.\n\n"
                    "A manager can release it, and the release is recorded.",
                    product=line.product_id.display_name,
                    bucket=dict(BUCKETS).get(self.bucket, self.bucket),
                    allowed=int(quota['allowed']), given=int(quota['given']),
                    left=int(quota['left']), asked=int(line.quantity)))

    def _freeze_cost(self):
        """Snapshot the cost at send time.

        Never live: the cost changes with the next print run, and a 2024 record
        would start telling a different story every time somebody reprints.
        """
        for rec in self:
            for line in rec.line_ids:
                if not line.unit_cost:
                    line.unit_cost = line.product_id.standard_price


class ProductBonusLine(models.Model):
    _name = 'product.bonus.line'
    _description = 'Bonus Copy Line'

    bonus_id = fields.Many2one('product.bonus', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.product', string="Title", required=True,
        domain=[('type', '=', 'consu')], ondelete='restrict', index=True)
    quantity = fields.Float(default=1.0, required=True)
    # The nota goes out at commercial value; the analytic must receive COST.
    # Two numbers in the same document -- do not let one become the other.
    unit_cost = fields.Float(
        string="Unit cost",
        help="Frozen when sent. This is the cash that left (print, paper), "
             "not the cover price.")
    subtotal = fields.Float(compute='_compute_subtotal', store=True)
    currency_id = fields.Many2one(related='bonus_id.currency_id')

    @api.depends('quantity', 'unit_cost')
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = rec.quantity * rec.unit_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.unit_cost = self.product_id.standard_price
