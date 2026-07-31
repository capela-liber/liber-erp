# -*- coding: utf-8 -*-
"""Picking the transporter inside Odoo's own 'Add shipping'.

The O15 connector -- and the first cut of this rewrite -- had a parallel
"print quote" window beside the native one, which meant two buttons doing the
same job and one of them lying whenever the other was used. There is only one
freight conversation now, and it is Odoo's: choose the Dropship method, hit
'Get rate', and every service Metabrasil quoted for that CEP shows up as a
line to pick from, cheapest (or fastest, per the carrier's rule) preselected.

The choice reaches delivery.carrier through the `metabrasil_option_id`
context key, so the price still travels the native pipeline (fiscal position,
then the carrier's margin) instead of a hand-rolled copy of it.
"""
from odoo import api, fields, models


class MetabrasilFreightOption(models.TransientModel):
    """One quoted transporter+service, alive for as long as the wizard is."""
    _name = 'metabrasil.freight.option'
    _description = 'Metabrasil Freight Option'
    _order = 'price, days, id'

    wizard_id = fields.Many2one(
        'choose.delivery.carrier', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    carrier_name = fields.Char(string='Transporter', required=True)
    carrier_vat = fields.Char(string='CNPJ')
    carrier_code = fields.Integer(string='Carrier Code')
    service_code = fields.Integer(string='Service Code')
    price = fields.Monetary(string='Freight', currency_field='currency_id')
    days = fields.Integer(string='Days')

    @api.depends('carrier_name', 'days')
    def _compute_display_name(self):
        for option in self:
            option.display_name = self.env._(
                "%(carrier)s — %(days)s day(s)",
                carrier=option.carrier_name or '?', days=option.days)

    def _rate_message(self):
        self.ensure_one()
        return self.env._("%(carrier)s, about %(days)s day(s).",
                          carrier=self.carrier_name, days=self.days)

    def _as_service(self):
        self.ensure_one()
        return {
            'carrier_name': self.carrier_name,
            'carrier_vat': self.carrier_vat or '',
            'carrier_code': self.carrier_code,
            'service_code': self.service_code,
            'price': self.price,
            'days': self.days,
        }


class ChooseDeliveryCarrier(models.TransientModel):
    _inherit = 'choose.delivery.carrier'

    metabrasil_option_ids = fields.One2many(
        'metabrasil.freight.option', 'wizard_id', string='Quoted Transporters')
    metabrasil_option_id = fields.Many2one(
        'metabrasil.freight.option', string='Transporter',
        domain="[('id', 'in', metabrasil_option_ids)]",
        help="Which transporter Metabrasil hands this print run to. Preset to "
             "the shipping method's own rule (cheapest or fastest); change it "
             "and the freight follows.")
    # Weight and volumes come back once per quote, not once per service, so
    # they belong to the wizard rather than to the options.
    metabrasil_totals = fields.Json(copy=False)

    def _metabrasil_load_options(self):
        """Re-quote and rebuild the option lines, keeping the salesperson's
        transporter selected when it is still on offer. Returns
        (options, quote payload)."""
        self.ensure_one()
        # The codes, not the record: the old rows are about to be unlinked
        # and a browse on a deleted one raises rather than compares.
        previous = (self.metabrasil_option_id.carrier_code,
                    self.metabrasil_option_id.service_code)
        services, totals = self.carrier_id.with_context(
            order_weight=self.total_weight).metabrasil_quote(self.order_id)
        self.metabrasil_option_ids.unlink()
        options = self.env['metabrasil.freight.option'].create([
            dict(service, wizard_id=self.id) for service in services])
        self.metabrasil_totals = {
            'totalWeight': float(totals.get('totalWeight') or 0.0),
            'totalVolumes': int(totals.get('totalVolumes') or 0),
        } if services else False
        same = options.filtered(
            lambda o: (o.carrier_code, o.service_code) == previous)
        # _metabrasil_services() already sorted by the carrier's Pick By rule
        # and create() preserved that order, so options[:1] IS the rule.
        self.metabrasil_option_id = same[:1] or options[:1]
        return options, totals

    def _get_delivery_rate(self):
        if self.delivery_type != 'metabrasil':
            return super()._get_delivery_rate()
        # Onchanges hand over a virtual record (an unsaved wizard, or an
        # existing one carrying pending changes); option rows can only be
        # written on a saved one, and re-picking a transporter asks not to
        # re-quote at all.
        if (isinstance(self.id, int)
                and not self.env.context.get('metabrasil_keep_options')):
            options, quote = self._metabrasil_load_options()
            if not options:
                self.delivery_message = False
                self.display_price = self.delivery_price = 0.0
                return {'error_message': self.env._(
                    "Metabrasil offers no freight service for this "
                    "destination (%s).",
                    quote.get('error') or self.order_id.partner_shipping_id.zip)}
        # _origin: in an onchange the selected option is a virtual copy of a
        # real row, and it is the real one the carrier has to read.
        option = self.metabrasil_option_id._origin
        if not option:
            return super()._get_delivery_rate()
        return super(ChooseDeliveryCarrier, self.with_context(
            metabrasil_option_id=option.id))._get_delivery_rate()

    @api.onchange('metabrasil_option_id')
    def _onchange_metabrasil_option_id(self):
        """Re-price from the option in hand -- no second call to Metabrasil,
        whose prices can move between two quotes of the same box."""
        if self.delivery_type != 'metabrasil' or not self.metabrasil_option_id:
            return
        vals = self.with_context(metabrasil_keep_options=True)._get_delivery_rate()
        if vals.get('error_message'):
            return {'warning': {
                'title': self.env._("%(carrier)s Error",
                                    carrier=self.carrier_id.name),
                'message': vals['error_message'],
                'type': 'notification'}}

    @api.onchange('carrier_id', 'total_weight')
    def _onchange_carrier_id(self):
        # A different shipping method (or a different weight) invalidates the
        # transporter list; the next 'Get rate' rebuilds it.
        res = super()._onchange_carrier_id()
        if self.delivery_type != 'metabrasil':
            self.metabrasil_option_id = False
        return res

    def button_confirm(self):
        # Onchanges must not write on the sale order, so the chosen service
        # only lands there here -- the last thing before the delivery line
        # exists.
        option = self.metabrasil_option_id._origin
        if self.delivery_type == 'metabrasil' and option:
            self.carrier_id._metabrasil_remember(
                self.order_id, option._as_service(), self.metabrasil_totals)
        return super().button_confirm()
