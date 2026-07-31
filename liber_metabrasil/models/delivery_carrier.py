# -*- coding: utf-8 -*-
"""The 'metabrasil' delivery type: freight quoted by the printer itself.

Metabrasil's /fretes/{cep}/rates/isbn returns every carrier they work with,
each with services priced with lead times. Two ways to land on one of them:

* automatic -- the carrier's own 'Pick By' rule (cheapest or fastest) takes
  the head of the sorted list. This is what any non-interactive caller gets;
* by hand -- 'Add shipping' lists every quoted service and the salesperson
  picks the transporter, which arrives here through the
  `metabrasil_option_id` context key.

Either way the sale order remembers the winning codes: the order POST needs
them for DROP_SHIP runs.

Deliberately NOT migrated from O15: creating res.partner records for every
carrier during a quote (cadastre pollution + race), and the website
calculator (freight is backend-only in this base).
"""
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('metabrasil', 'Metabrasil')],
        ondelete={'metabrasil': 'set default'})
    metabrasil_service_choice = fields.Selection(
        [('cheap', 'Cheapest'), ('fast', 'Fastest')],
        string='Pick By', default='cheap',
        help="Which of the services Metabrasil offers is preselected in the "
             "quote: the lowest price or the shortest lead time. The "
             "salesperson can still pick another transporter by hand.")
    metabrasil_excluded_carriers = fields.Char(
        string='Excluded Carriers',
        help="Comma-separated carrier names to ignore when quoting (e.g. a "
             "transporter that keeps losing boxes). Leave empty to accept "
             "them all.")

    def _metabrasil_services(self, carriers_payload):
        """Flatten Metabrasil's shippingCarrier[].shippingServices[] into a
        sorted list of dicts; first element wins."""
        self.ensure_one()
        excluded = {name.strip().lower()
                    for name in (self.metabrasil_excluded_carriers or '').split(',')
                    if name.strip()}
        services = []
        for carrier in carriers_payload or []:
            if (carrier.get('name') or '').lower() in excluded:
                continue
            for service in carrier.get('shippingServices') or []:
                try:
                    services.append({
                        'carrier_name': carrier.get('name') or '',
                        'carrier_vat': carrier.get('cnpj') or '',
                        'carrier_code': int(carrier.get('code') or 0),
                        'service_code': int(service.get('code') or 0),
                        'price': float(service.get('price')),
                        'days': int(float(service.get('days') or 0)),
                    })
                except (TypeError, ValueError):
                    _logger.warning("Metabrasil rate entry skipped: %s / %s",
                                    carrier, service)
        key = ((lambda s: s['price']) if self.metabrasil_service_choice == 'cheap'
               else (lambda s: (s['days'], s['price'])))
        return sorted(services, key=key)

    def metabrasil_quote(self, order):
        """(services, totals) for this order's shipping address.

        The whole offer, not just the winner: 'Add shipping' shows the list so
        the transporter is a choice rather than a rule.
        """
        self.ensure_one()
        items = order._metabrasil_quote_items()
        if not items:
            return [], {'error': self.env._(
                "Nothing to quote: the order has no storable lines.")}
        code, data = self.env['metabrasil.api'].freight_rates(
            order.company_id, order.partner_shipping_id.zip, items)
        if code != 200:
            return [], data
        return self._metabrasil_services(data.get('shippingCarrier')), data

    def _metabrasil_remember(self, order, service, totals=None):
        """Persist the winning service on the sale: the order POST needs the
        codes later, and re-quoting at confirmation could silently pick a
        different transporter than the one the customer priced."""
        if not order.id:
            return
        values = {
            'metabrasil_carrier_name': service['carrier_name'],
            'metabrasil_carrier_vat': service['carrier_vat'],
            'metabrasil_carrier_code': service['carrier_code'],
            'metabrasil_service_code': service['service_code'],
            'metabrasil_delivery_days': service['days'],
            'metabrasil_freight_cost': service['price'],
        }
        if totals:
            values.update(
                metabrasil_total_weight=float(totals.get('totalWeight') or 0.0),
                metabrasil_total_volumes=int(totals.get('totalVolumes') or 0))
        order.write(values)

    def metabrasil_rate_shipment(self, order):
        self.ensure_one()
        # 'Add shipping' has already quoted and the salesperson has picked a
        # transporter: honour it instead of asking Metabrasil again -- a
        # second call can come back with different prices mid-decision.
        chosen = self.env['metabrasil.freight.option'].browse(
            self.env.context.get('metabrasil_option_id') or []).exists()
        if chosen:
            return {
                'success': True,
                'price': chosen.price,  # rate_shipment() applies the margin
                'error_message': False,
                'warning_message': chosen._rate_message(),
            }

        services, data = self.metabrasil_quote(order)
        if not services:
            return {'success': False, 'price': 0.0, 'warning_message': False,
                    'error_message': self.env._(
                        "Metabrasil offers no freight service for this "
                        "destination (%s).",
                        data.get('error') or order.partner_shipping_id.zip)}
        best = services[0]
        self._metabrasil_remember(order, best, data)
        return {
            'success': True,
            'price': best['price'],  # rate_shipment() applies the margin
            'error_message': False,
            'warning_message': self.env._(
                "%(carrier)s, about %(days)s day(s).",
                carrier=best['carrier_name'], days=best['days']),
        }

    def metabrasil_send_shipping(self, pickings):
        # Nothing to book on their side: the shipment IS the print order,
        # already POSTed from the purchase. Report the remembered price and
        # whatever tracking the status cron has brought home.
        return [{'exact_price': picking.sale_id.metabrasil_freight_cost or 0.0,
                 'tracking_number': picking.carrier_tracking_ref or False}
                for picking in pickings]

    def metabrasil_get_tracking_link(self, picking):
        return picking.metabrasil_tracking_url or False

    def metabrasil_cancel_shipment(self, pickings):
        pass  # cancellation travels through the purchase order, not here
