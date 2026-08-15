# -*- coding: utf-8 -*-
from odoo import fields, models


class DeliveryCarrier(models.Model):
    """O método de entrega ganha a empresa por trás dele.

    No core, delivery.carrier é só um nome com preço — não há quem
    telefonar nem para quem escrever. O partner dá corpo à transportadora
    (e-mail, CNPJ, endereço) sem duplicar cadastro: é um contato comum.
    """
    _inherit = 'delivery.carrier'

    partner_id = fields.Many2one(
        'res.partner', string='Carrier Company',
        help="The transport company behind this delivery method. Its e-mail "
             "address receives the pickup requests sent from the delivery "
             "orders list — or the address of its Delivery contact, when it "
             "has one.")

    def _pickup_contact(self):
        """A quem escrever nesta transportadora.

        Transportadora grande não atende coleta na caixa geral: tem uma
        mesa de coletas, que no cadastro é um contato do tipo Entregas
        dentro da empresa. Quando existe e tem e-mail, é ele que recebe;
        senão, a própria empresa. (Dentro da TRANSPORTADORA — o mesmo
        contato dentro do cliente seria endereço de destino, outra coisa.)
        """
        self.ensure_one()
        empresa = self.partner_id
        if not empresa:
            return empresa
        entregas = self.env['res.partner'].browse(
            empresa.address_get(['delivery']).get('delivery'))
        return entregas if entregas.email else empresa
