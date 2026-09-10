# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fair_shipment_fiscal_position_id = fields.Many2one(
        'account.fiscal.position', string='Fair Shipment Fiscal Position',
        help="Remessa para exposição ou feira (CFOP 5.914 / 6.914). It needs "
             "Auto Invoice Paid with its account, and exactly one account "
             "mapping starting on a revenue account: a remessa is not "
             "revenue, and the map is what moves it out of revenue.")
    fair_return_fiscal_position_id = fields.Many2one(
        'account.fiscal.position', string='Fair Return Fiscal Position',
        help="Retorno de mercadoria remetida para exposição ou feira "
             "(CFOP 1.914 / 2.914). Not used yet: the return note comes with "
             "the return count.")

    def _remessa_fiscal_position_by_kind(self):
        mapa = super()._remessa_fiscal_position_by_kind()
        mapa['event'] = self.fair_shipment_fiscal_position_id
        return mapa
