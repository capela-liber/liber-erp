# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PickupRequest(models.Model):
    """O lote de coleta: um pedido, uma transportadora, N entregas.

    Existe porque a solicitação precisa sobreviver ao clique. O e-mail
    mora no histórico daqui (não num registro temporário que o sistema
    descarta), a transportadora responde para cá — resposta cai no
    histórico pelo caminho normal do e-mail — e a logística acompanha o
    estado até a carga sair: Rascunho -> Enviada -> Coletada.

    O número (COL/ano/00001) é o que se cita ao telefone.
    """
    _name = 'liber.transport.pickup.request'
    _description = 'Pickup Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Reference', required=True, readonly=True, copy=False,
        default=lambda self: _('New'))
    carrier_id = fields.Many2one(
        'delivery.carrier', string='Carrier', required=True,
        readonly=False, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', related='carrier_id.partner_id',
        string='Carrier Company', store=True, readonly=True)
    # Computado mas gravável: o padrão é a mesa de coletas da transportadora
    # (contato de Entregas), e o operador pode desviar para outra pessoa
    # antes de enviar sem mexer no cadastro.
    contact_id = fields.Many2one(
        'res.partner', string='Pickup Contact',
        compute='_compute_contact_id', store=True, readonly=False,
        help="Who receives this request at the carrier: its Delivery "
             "contact when there is one, otherwise the company itself.")
    email = fields.Char(related='contact_id.email', string='E-mail')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    picking_ids = fields.Many2many(
        'stock.picking', 'liber_transport_request_picking_rel',
        'request_id', 'picking_id', string='Delivery Orders')
    picking_count = fields.Integer(compute='_compute_picking_count')
    # O que a transportadora precisa saber para mandar o veículo certo.
    total_box_count = fields.Integer(
        string='Boxes', compute='_compute_totals')
    total_weight = fields.Float(
        string='Weight', digits='Stock Weight', compute='_compute_totals')
    state = fields.Selection(
        [('draft', 'Draft'), ('sent', 'Sent'), ('done', 'Collected'),
         ('cancel', 'Cancelled')],
        string='Status', default='draft', required=True, tracking=True)
    request_date = fields.Datetime(
        string='Requested On', readonly=True, copy=False,
        help="When the request was e-mailed to the carrier.")
    scheduled_date = fields.Date(
        string='Agreed Pickup Date', tracking=True,
        help="Date the carrier confirmed for the pickup. Filled by "
             "logistics when the answer arrives.")
    carrier_reference = fields.Char(
        string='Carrier Reference', tracking=True, copy=False,
        help="The number the carrier gives to this pickup, if any. What "
             "you quote on the phone when chasing it.")

    @api.depends('carrier_id')
    def _compute_contact_id(self):
        for request in self:
            request.contact_id = request.carrier_id._pickup_contact()

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for request in self:
            request.picking_count = len(request.picking_ids)

    @api.depends('picking_ids.box_count', 'picking_ids.shipping_weight',
                 'picking_ids.weight')
    def _compute_totals(self):
        for request in self:
            request.total_box_count = sum(request.picking_ids.mapped('box_count'))
            request.total_weight = sum(
                p._liber_peso_para_transporte() for p in request.picking_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                company = vals.get('company_id') or self.env.company.id
                vals['name'] = self.env['ir.sequence'].with_company(
                    company).next_by_code(
                        'liber.transport.pickup.request') or _('New')
        return super().create(vals_list)

    # --- envio ------------------------------------------------------------

    def _pickup_body(self):
        """Assunto, corpo e remetente, renderizados do template.

        O ``email_from`` tem de vir do template (a casa antes do usuário):
        message_post, sozinho, assina com o e-mail de quem clicou — e a
        transportadora receberia uma coleta vinda do endereço pessoal do
        conferente, não do comercial da editora.
        """
        self.ensure_one()
        template = self.env.ref(
            'liber_transport.mail_template_pickup_request',
            raise_if_not_found=False)
        if not template:
            return False, False, False
        subject = template._render_field('subject', self.ids)[self.id]
        body = template._render_field(
            'body_html', self.ids, compute_lang=True)[self.id]
        email_from = template._render_field('email_from', self.ids)[self.id]
        return subject, body, email_from

    def action_send(self):
        for request in self:
            if request.state == 'cancel':
                raise UserError(_(
                    "%s is cancelled — reopen it before sending.",
                    request.name))
            if not request.email:
                raise UserError(_(
                    "%(carrier)s has no e-mail address. Fill it in on the "
                    "carrier company (%(partner)s) and send again.",
                    carrier=request.carrier_id.name,
                    partner=request.partner_id.display_name or _('missing')))
            subject, body, email_from = request._pickup_body()
            if not body:
                raise UserError(_("The pickup request e-mail template is missing."))
            # message_post (não template.send_mail): assim o e-mail FICA no
            # histórico do lote, e a resposta da transportadora volta para cá.
            # force_send=False deixa a fila cuidar do envio.
            request.with_context(mail_notify_force_send=False).message_post(
                body=body, subject=subject,
                email_from=email_from,
                author_id=self.env.user.partner_id.id,
                partner_ids=request.contact_id.ids,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                email_layout_xmlid='mail.mail_notification_light')
            request.write({
                'state': 'sent',
                'request_date': fields.Datetime.now(),
            })
            request._stamp_pickings()
        return True

    def _stamp_pickings(self):
        """Carimba a data e deixa o rastro no histórico de cada entrega."""
        self.ensure_one()
        link = Markup(
            '<a href=# data-oe-model=liber.transport.pickup.request '
            'data-oe-id=%d>%s</a>') % (self.id, self.name)
        outras = len(self.picking_ids) - 1
        for picking in self.picking_ids:
            if outras:
                body = _(
                    "Pickup requested from %(carrier)s (%(email)s) — request "
                    "%(link)s, together with %(count)s other delivery order(s).",
                    carrier=self.carrier_id.name, email=self.email,
                    link=link, count=outras)
            else:
                body = _(
                    "Pickup requested from %(carrier)s (%(email)s) — request "
                    "%(link)s.",
                    carrier=self.carrier_id.name, email=self.email, link=link)
            picking.message_post(body=body, subtype_xmlid='mail.mt_note')
        self.picking_ids.write({'pickup_request_date': self.request_date})

    # --- ciclo de vida ----------------------------------------------------

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_view_pickings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery Orders'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.picking_ids.ids)],
        }
