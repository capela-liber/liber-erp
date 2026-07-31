# -*- coding: utf-8 -*-
"""The print order: a purchase order whose vendor is the printer.

Lifecycle: approve the PO -> POST /pedidos -> the cron mirrors Metabrasil's
status ladder back (included -> printing -> shipped -> delivered), carrying
tracking codes to the picking, optionally validating the receipt and drafting
the vendor bill, and e-mailing the customer of direct deliveries.

Two error philosophies, one per direction. On the way OUT (confirm -> send),
a rejection RAISES: the confirmation rolls back and the order stays an RFQ, so
there is never a confirmed-but-rejected print order to babysit -- fix the
cause and confirm again. On the way IN (the status cron reading dozens of
orders), a failure must NOT raise -- it would roll back the whole sweep; there
it writes the status, posts the reason and schedules an activity, and the
transaction survives.
"""
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Metabrasil's statusPedido strings -> our slugs. Their API speaks accented
# Portuguese; our database speaks slugs (house i18n rule: English source,
# pt_BR.po on top).
API_STATUS_MAP = {
    'Pedido Incluído': 'included',
    'Impressão': 'printing',
    'Expedido': 'shipped',
    'Entregue': 'delivered',
    'Cancelado': 'cancelled',
}
FINAL_STATUSES = ('delivered', 'cancelled')


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    metabrasil_status = fields.Selection(
        [('not_sent', 'Not Sent'),
         ('included', 'Order Included'),
         ('printing', 'In Production'),
         ('shipped', 'Shipped'),
         ('delivered', 'Delivered'),
         ('cancelled', 'Cancelled'),
         ('error', 'Error'),
         ('not_found', 'Not Found')],
        string='Print Status', default='not_sent', copy=False, tracking=True,
        help="Metabrasil's view of this print order, mirrored by the sync "
             "cron. Error means the last call failed -- fix the cause and "
             "use 'Send to Metabrasil' to retry.")
    metabrasil_sent = fields.Boolean(
        string='Sent to Metabrasil', copy=False, readonly=True)
    metabrasil_order_ref = fields.Char(
        string='Metabrasil Reference', copy=False, readonly=True,
        help="codigoEncomenda in their system; the key the status cron asks "
             "about.")
    metabrasil_sync_date = fields.Datetime(
        string='Last Print Sync', copy=False, readonly=True)
    is_metabrasil = fields.Boolean(
        string='Is Print Order', compute='_compute_is_metabrasil')
    metabrasil_delivery_kind = fields.Selection(
        [('warehouse', 'PoD'), ('customer', 'Dropship')],
        string='Print Delivery Kind', compute='_compute_metabrasil_delivery_kind',
        help="How this print order reaches its destination: a dropship "
             "address means the books go straight to the customer, its "
             "absence that they land at our depot. Drives the corner ribbon "
             "so PoD vs Dropship is evident without opening the route.")
    metabrasil_sale_order_id = fields.Many2one(
        'sale.order', string='Print For',
        compute='_compute_metabrasil_sale_order',
        help="The sale this print run serves, through the real line-to-line "
             "link -- the same one the Metabrasil payload reads for the "
             "delivery address and the freight.")

    @api.depends('order_line.sale_line_id.order_id')
    def _compute_metabrasil_sale_order(self):
        for po in self:
            po.metabrasil_sale_order_id = po._metabrasil_get_sale_order()

    @api.depends('partner_id', 'company_id.metabrasil_enabled',
                 'company_id.metabrasil_partner_id')
    def _compute_is_metabrasil(self):
        for po in self:
            po.is_metabrasil = bool(
                po.company_id.metabrasil_enabled
                and po.partner_id
                and po.partner_id == po.company_id.metabrasil_partner_id)

    @api.depends('is_metabrasil', 'dest_address_id')
    def _compute_metabrasil_delivery_kind(self):
        for po in self:
            po.metabrasil_delivery_kind = (
                po._metabrasil_delivery_mode() if po.is_metabrasil else False)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def button_approve(self, force=False):
        res = super().button_approve(force=force)
        for po in self.filtered(lambda p: p.is_metabrasil and p.metabrasil_status
                                in ('not_sent', 'error', 'not_found', 'cancelled')):
            po._metabrasil_send()
        return res

    def action_metabrasil_refresh(self):
        """Ask Metabrasil about these orders right now (list/form button)."""
        self.filtered(lambda p: p.is_metabrasil and p.metabrasil_sent
                      )._metabrasil_sync_status()

    def _metabrasil_send(self):
        self.ensure_one()
        payload = self._metabrasil_prepare_payload()
        code, data = self.env['metabrasil.api'].post_order(self.company_id, payload)
        if code == 0:
            return  # not configured; stay silent like any other vendor
        if code == 200:
            self.write({
                'metabrasil_sent': True,
                'metabrasil_status': 'included',
                'metabrasil_order_ref': data.get('codigoEncomenda') or self.name,
                'metabrasil_sync_date': fields.Datetime.now(),
            })
            self.message_post(body=self.env._(
                "Print order sent to Metabrasil (reference %s).",
                self.metabrasil_order_ref))
        else:
            # Block the confirmation itself: raising here rolls back the state
            # change super() just made, so the order stays an RFQ instead of
            # sitting confirmed-but-rejected. Fix the cause (register the ISBN
            # in the POD, complete the address) and confirm again -- there is
            # no separate resend, because re-confirming IS the resend.
            raise UserError(self.env._(
                "Metabrasil did not accept this print order, so it was not "
                "confirmed. Fix the cause and confirm again:\n\n%s",
                self.env['metabrasil.api'].error_text(data)))

    def _metabrasil_register_failure(self, reason):
        """Persist the failure where people will see it: status, chatter,
        activity. Never raises -- raising would roll the status back."""
        self.ensure_one()
        self.write({'metabrasil_status': 'error',
                    'metabrasil_sync_date': fields.Datetime.now()})
        self.message_post(body=reason)
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=self.env._("Metabrasil call failed"),
            note=reason,
            user_id=(self.user_id or self.env.user).id)

    # ------------------------------------------------------------------
    # Payload
    # ------------------------------------------------------------------
    @api.model
    def _metabrasil_split_street(self, street):
        """'Rua João XXIII, 987' -> ('Rua João XXIII', '987').

        Addresses in this base carry the number inside the street line (no
        l10n_br split fields here); Metabrasil wants them apart. No trailing
        number found -> the whole line is the street and the number is S/N.
        """
        street = (street or '').strip()
        match = re.match(r'^(?P<name>.+?)[,\s]+(?P<number>\d+[\w/-]*)$', street)
        if match:
            return match.group('name').rstrip(',').strip(), match.group('number')
        return street, 'S/N'

    @api.model
    def _metabrasil_address_block(self, partner, suffix=''):
        street, number = self._metabrasil_split_street(partner.street)
        return {
            'nome' + suffix if suffix else 'nomeCliente': partner.name or '',
            'logradouro' + suffix: street,
            ('numero' + suffix) if suffix else 'numero_comprador': number,
            # No l10n_br here, so no structured district field: street2 carries
            # the neighbourhood, which Metabrasil requires (bairro_entrega) --
            # a missing one is a hard 400 on /pedidos. Complemento loses its
            # home in the trade; add l10n_br if both are ever needed at once.
            'bairro' + suffix: partner.street2 or '',
            'complemento' + suffix: '',
            'cep' + suffix: partner.zip or '',
            'cidade' + suffix: partner.city or '',
            'uf' + suffix: partner.state_id.code or '',
            'pais' + suffix: partner.country_id.code or '',
            'fone' + suffix: partner.phone or '',
        }

    def _metabrasil_get_sale_order(self):
        """The sale order this print run serves, through the real link
        (sale_purchase's sale_line_id), not a search by name."""
        self.ensure_one()
        return self.order_line.sale_line_id.order_id[:1]

    def _metabrasil_delivery_mode(self):
        """Dropship or depot, read from the destination address rather than
        declared.

        There used to be a 'Print Delivery' selection on the sale, plus a
        wizard to set it; it was a second place to say what the dropship
        route already says -- and the two could disagree. A print order with
        a dest_address_id IS a dropship (that address is the customer's);
        without one the run lands at our depot and we ship it ourselves.
        """
        self.ensure_one()
        return 'customer' if self.dest_address_id else 'warehouse'

    def _metabrasil_prepare_payload(self):
        self.ensure_one()
        company = self.company_id
        buyer = company.partner_id
        sale_order = self._metabrasil_get_sale_order()
        mode = self._metabrasil_delivery_mode()
        ship_to = self.dest_address_id or buyer

        data = {
            'chaveCliente': company.metabrasil_access_key,
            'codigoEncomenda': self.name,
            'cpf_cnpj': re.sub(r'\D', '', buyer.vat or ''),
            'email': buyer.email or '',
            'data': (self.create_date or fields.Datetime.now()).isoformat(),
            'valor_pedido': (sale_order.amount_total if sale_order
                             else self.amount_total),
            'valor_frete': (sale_order.metabrasil_freight_cost
                            if sale_order else 0.0),
        }
        data.update(self._metabrasil_address_block(buyer))
        data.update(self._metabrasil_address_block(ship_to, '_entrega'))

        if mode == 'customer':
            data.update({
                'pedidoType': 'DROP_SHIP',
                'metodo_envio': False,
                'cnpjTransportadora': re.sub(
                    r'\D', '', sale_order.metabrasil_carrier_vat or ''
                ) if sale_order else '',
                'shippingCarrierCode': (sale_order.metabrasil_carrier_code
                                        if sale_order else 0),
                'shippingServicesCode': (sale_order.metabrasil_service_code
                                         if sale_order else 0),
            })
        else:
            data.update({
                'pedidoType': 'EDITORA',
                'metodo_envio': ('RETIRADA'
                                 if company.metabrasil_warehouse_transport == 'pickup'
                                 else 'CARRO META'),
                'cnpjTransportadora': '',
            })

        items = []
        for sequence, line in enumerate(
                (l for l in self.order_line
                 if l.product_id.type != 'service' and not l.display_type),
                start=1):
            items.append({
                'referenciaISBN': str(line.product_id.barcode
                                      or line.product_id.default_code or ''),
                'descricao': line.product_id.name,
                'itemType': 'LIVRO',
                'moeda': self.currency_id.name,
                'orderItemId': sequence,
                'quantidade': float(line.product_qty),
                'preco': float(line.product_id.lst_price),
            })
        data['listaItems'] = items
        return data

    # ------------------------------------------------------------------
    # Status sync (cron + manual refresh)
    # ------------------------------------------------------------------
    @api.model
    def _cron_metabrasil_sync_status(self):
        orders = self.search([
            ('company_id.metabrasil_enabled', '=', True),
            ('metabrasil_sent', '=', True),
            ('metabrasil_status', 'not in', FINAL_STATUSES),
            ('state', 'not in', ('draft', 'sent', 'cancel')),
        ])
        _logger.info("Metabrasil status sync: %s order(s)", len(orders))
        orders._metabrasil_sync_status()

    def _metabrasil_sync_status(self):
        api_model = self.env['metabrasil.api']
        for po in self:
            code, data = api_model.get_order(
                po.company_id, po.metabrasil_order_ref or po.name)
            if code == 0:
                continue
            if code == 200:
                po._metabrasil_apply_status(data)
            elif code == 400:
                po.write({'metabrasil_status': 'not_found',
                          'metabrasil_sync_date': fields.Datetime.now()})
                po.message_post(body=self.env._(
                    "Metabrasil does not know order %s.",
                    po.metabrasil_order_ref or po.name))
            else:
                po._metabrasil_register_failure(self.env._(
                    "Could not read the print status from Metabrasil: %s",
                    api_model.error_text(data)))

    def _metabrasil_apply_status(self, data):
        self.ensure_one()
        slug = API_STATUS_MAP.get(data.get('statusPedido') or '')
        previous = self.metabrasil_status
        values = {'metabrasil_sync_date': fields.Datetime.now()}
        if data.get('codigoEncomenda'):
            values['metabrasil_order_ref'] = data['codigoEncomenda']
        if slug:
            values['metabrasil_status'] = slug
        self.write(values)
        if not slug or slug == previous:
            return
        self.message_post(body=self.env._(
            "Metabrasil print status: %s", data.get('statusPedido')))
        if slug == 'cancelled':
            self._metabrasil_on_cancelled()
        elif slug in ('shipped', 'delivered'):
            self._metabrasil_on_shipped(data, slug)
        if slug in ('printing', 'delivered'):
            self._metabrasil_notify_customer(slug)

    def _metabrasil_on_cancelled(self):
        self.ensure_one()
        try:
            self.button_cancel()
            self.message_post(body=self.env._(
                "Print order cancelled by Metabrasil."))
        except Exception as exc:  # noqa: BLE001 - cancellation is best-effort
            self.message_post(body=self.env._(
                "Metabrasil cancelled this print order but it could not be "
                "cancelled here: %s", exc))

    def _metabrasil_on_shipped(self, data, slug):
        """Tracking onto the picking; optionally validate the receipt and
        draft the bill -- each behind its Settings knob."""
        self.ensure_one()
        today = fields.Date.today()
        pickings = self.picking_ids.filtered(
            lambda p: p.state not in ('done', 'cancel'))
        done = self.picking_ids.filtered(lambda p: p.state == 'done')
        for picking in pickings:
            if data.get('codigoRastreio') and not picking.carrier_tracking_ref:
                picking.carrier_tracking_ref = data['codigoRastreio']
            if data.get('urlRastreio') and not picking.metabrasil_tracking_url:
                picking.metabrasil_tracking_url = data['urlRastreio']
        for picking in (pickings | done):
            if slug == 'shipped' and not picking.metabrasil_shipped_date:
                picking.metabrasil_shipped_date = today
            if slug == 'delivered' and not picking.metabrasil_delivered_date:
                picking.metabrasil_delivered_date = today

        if self.company_id.metabrasil_auto_validate_picking:
            for picking in pickings.filtered(
                    lambda p: p.state in ('assigned', 'confirmed')):
                try:
                    picking.with_context(
                        skip_backorder=True, skip_sms=True).button_validate()
                    picking.message_post(body=self.env._(
                        "Receipt validated automatically: Metabrasil reports "
                        "the print order as %s.", slug))
                except Exception as exc:  # noqa: BLE001 - keep the cron alive
                    picking.message_post(body=self.env._(
                        "Could not auto-validate this receipt: %s", exc))

        if (self.company_id.metabrasil_auto_create_bill
                and self.invoice_status == 'to invoice'):
            try:
                self.action_create_invoice()
                self.message_post(body=self.env._(
                    "Vendor bill drafted from the shipped print order."))
            except Exception as exc:  # noqa: BLE001
                self.message_post(body=self.env._(
                    "Could not draft the vendor bill: %s", exc))

    def _metabrasil_notify_customer(self, slug):
        """E-mail the customer of a direct delivery when the run enters
        production and when it lands."""
        self.ensure_one()
        if not self.company_id.metabrasil_send_status_mails:
            return
        sale_order = self._metabrasil_get_sale_order()
        if not sale_order or not self.dest_address_id:
            return  # warehouse runs are our own business
        ref = ('liber_metabrasil.mail_template_metabrasil_printing'
               if slug == 'printing'
               else 'liber_metabrasil.mail_template_metabrasil_delivered')
        template = self.env.ref(ref, raise_if_not_found=False)
        if template:
            template.send_mail(sale_order.id)

    # ------------------------------------------------------------------
    # Fiscal PATCH -- the liber_olist hook
    # ------------------------------------------------------------------
    def _metabrasil_fiscal_patch(self):
        """PATCH /pedidos with the DANFE link and Correios data.

        Emission does not exist in this base yet (it is deferred to the
        Olist adapter); when liber_olist lands it overrides this with the
        real thing. Kept as an explicit hook so the call site is already
        wired.
        """
        self.ensure_one()

    # ------------------------------------------------------------------
    # Overdue sweeps
    # ------------------------------------------------------------------
    @api.model
    def _cron_metabrasil_exceptions(self):
        """Daily: raise an activity on print orders that stalled -- waiting
        for approval, past their scheduled shipping date, or past their
        expected delivery. One activity per reason, never duplicated."""
        yesterday = fields.Datetime.subtract(fields.Datetime.now(), days=1)
        now = fields.Datetime.now()
        domain_base = [('company_id.metabrasil_enabled', '=', True),
                       ('company_id.metabrasil_exception_activities', '=', True)]

        stalled = self.search(domain_base + [
            ('state', 'in', ('draft', 'sent')),
            ('create_date', '<', yesterday)])
        for po in stalled.filtered('is_metabrasil'):
            po._metabrasil_exception_activity(
                self.env._("Print order awaiting approval"),
                self.env._("This print order was not approved within a day; "
                           "Metabrasil has not received it yet."))

        in_flight = self.search(domain_base + [
            ('state', '=', 'purchase'),
            ('metabrasil_sent', '=', True),
            ('metabrasil_status', 'not in', FINAL_STATUSES)])
        for po in in_flight.filtered('is_metabrasil'):
            picking = po.picking_ids.filtered(
                lambda p: p.state not in ('done', 'cancel'))[:1]
            if not picking:
                continue
            if (po.metabrasil_status not in ('shipped',)
                    and picking.scheduled_date
                    and picking.scheduled_date < now
                    and not picking.metabrasil_shipped_date):
                po._metabrasil_exception_activity(
                    self.env._("Print order not shipped on time"),
                    self.env._("Metabrasil has not shipped this order by its "
                               "scheduled date."))
            elif (picking.metabrasil_shipped_date
                    and not picking.metabrasil_delivered_date
                    and picking.scheduled_date
                    and picking.scheduled_date < yesterday):
                po._metabrasil_exception_activity(
                    self.env._("Print order not delivered on time"),
                    self.env._("This order shipped but has not been reported "
                               "delivered by its expected date."))

    def _metabrasil_exception_activity(self, summary, note):
        self.ensure_one()
        existing = self.env['mail.activity'].sudo().search_count([
            ('res_model', '=', 'purchase.order'),
            ('res_id', '=', self.id),
            ('summary', '=', summary)])
        if not existing:
            self.activity_schedule(
                'mail.mail_activity_data_todo', summary=summary, note=note,
                user_id=(self.user_id or self.env.user).id)
