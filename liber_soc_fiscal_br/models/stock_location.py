# -*- coding: utf-8 -*-
from odoo import models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    def _should_be_valued(self):
        """A consignment shelf holds our goods physically (usage='internal', so
        quantities keep counting in On Hand / on_shelf_qty), but its *value* is
        re-qualified into the shelf's own valuation account (115000) rather than
        the warehouse Inventory account.

        Returning False here is the single lever that makes stock_account treat a
        warehouse -> shelf move as a valued *out* (Dr 115000 / Cr Inventory) and a
        shelf -> warehouse move as a valued *in* (Dr Inventory / Cr 115000).
        Nothing else in the consignment model changes: the shelf stays internal
        and its quants stay ours.
        """
        self.ensure_one()
        if self.usage == 'internal' and self.is_consignment_shelf:
            return False
        return super()._should_be_valued()
