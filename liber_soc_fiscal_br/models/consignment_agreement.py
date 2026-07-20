# -*- coding: utf-8 -*-
from odoo import models


class ConsignmentAgreement(models.Model):
    _inherit = 'consignment.agreement'

    def _create_shelf_location(self):
        """Stamp the consignment stock account on the shelf as it is created, so
        stock_account re-qualifies its value into that account."""
        location = super()._create_shelf_location()
        account = self.company_id.consignment_stock_account_id
        if account:
            location.valuation_account_id = account.id
        return location
