# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    """A saída nasce sabendo quem a leva.

    O carrier do cliente (property_delivery_carrier_id) só chega ao picking
    pelo passo de frete da venda ("Add shipping"), que a casa não usa. O hook
    de create abaixo aplica o carrier do cliente a toda saída que chegar sem
    um — e nunca por cima de um que já veio nos vals, então o fluxo nativo
    (wizard + propagate_carrier) continua mandando quando existir.
    """
    _inherit = 'stock.picking'

    # Caixa ninguém calcula: quem embala conta. O peso o Odoo soma dos
    # produtos (stock_delivery), mas a caixa é decisão de bancada — cabe
    # mais livro ou não cabe —, e é ela que a nota fiscal declara e a
    # transportadora precisa saber para separar o caminhão.
    box_count = fields.Integer(
        string='Boxes', copy=False,
        help="How many boxes this delivery ships in. Counted by whoever "
             "packs it: the fiscal note declares it and the carrier plans "
             "the truck by it.")
    pickup_request_date = fields.Datetime(
        string='Pickup Requested On', readonly=True, copy=False,
        help="When the pickup request for this delivery was last e-mailed "
             "to the carrier.")
    # Muitos porque recoleta acontece: a entrega que não saiu na primeira
    # chamada entra na seguinte, e as duas ficam no histórico.
    pickup_request_ids = fields.Many2many(
        'liber.transport.pickup.request',
        'liber_transport_request_picking_rel', 'picking_id', 'request_id',
        string='Pickup Requests', readonly=True, copy=False,
        help="Pickup requests this delivery was included in.")

    def _liber_peso_para_transporte(self):
        """O peso que vale para a coleta e para a nota, em quilos.

        O ``weight`` do core é campo ARMAZENADO e só se refaz quando a linha
        muda: cadastrar o peso do livro depois não recalcula movimento
        antigo, e o número fica velho em silêncio. Por isso aqui se soma o
        peso ao vivo dos produtos — a não ser que alguém tenha digitado o
        peso de expedição, que é medida de balança e ganha de qualquer conta.
        """
        self.ensure_one()
        return self.shipping_weight or self._get_estimated_weight()

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        pickings._liber_transport_set_default_carrier()
        return pickings

    def _liber_transport_set_default_carrier(self):
        for picking in self:
            if (picking.picking_type_code != 'outgoing'
                    or picking.carrier_id or not picking.partner_id):
                continue
            # A property é company-dependent: sem with_company, um create
            # rodando noutra empresa do env leria o valor errado. O fallback
            # ao commercial_partner_id copia o wizard do core: o endereço de
            # entrega filho raramente carrega a property, a livraria-mãe sim.
            partner = picking.partner_id.with_company(picking.company_id)
            carrier = (
                partner.property_delivery_carrier_id.filtered('active')
                or partner.commercial_partner_id
                    .property_delivery_carrier_id.filtered('active')
            )
            if carrier and carrier.company_id.id in (False, picking.company_id.id):
                picking.carrier_id = carrier
