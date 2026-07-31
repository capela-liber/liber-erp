# -*- coding: utf-8 -*-
"""Reading the price ladder against what the book is supposed to cost.

A vendor price list is a wall of numbers. Two things make it legible: the
print run each price belongs to (useless without it -- four lines of the same
book differ only by quantity), and whether a given line is *worse* than the
cost we carry the book at, which is the moment print-on-demand stops paying
for itself.
"""
from odoo import api, fields, models


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

    metabrasil_product_cost = fields.Monetary(
        string='Product Cost', compute='_compute_metabrasil_cost_flag',
        currency_field='currency_id',
        help="The book's own cost, converted into this line's currency so the "
             "two numbers can be read side by side.")
    metabrasil_above_cost = fields.Boolean(
        string='Above Cost', compute='_compute_metabrasil_cost_flag',
        help="This vendor price is higher than what we carry the book at: "
             "printing this run costs more than the book is worth to us.")

    @api.depends('price', 'currency_id', 'product_tmpl_id.standard_price',
                 'product_id.standard_price', 'company_id')
    def _compute_metabrasil_cost_flag(self):
        for line in self:
            product = line.product_id or line.product_tmpl_id
            company = line.company_id or self.env.company
            cost = product.standard_price if product else 0.0
            # standard_price lives in the company's currency and the printer
            # quotes in its own, so a raw comparison would be nonsense on a
            # company that does not happen to keep books in BRL.
            if cost and line.currency_id and company.currency_id != line.currency_id:
                cost = company.currency_id._convert(
                    cost, line.currency_id, company,
                    fields.Date.context_today(line))
            line.metabrasil_product_cost = cost
            line.metabrasil_above_cost = bool(cost) and line.price > cost
