# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _bonus_print_run(self):
        """The print run is the stock -- but the ENTRIES, not the balance.

        The balance falls as the book sells; a print run of 3000 stays 3000. So
        "% of the print run" has to read what came IN. A reprint adds to it
        (3000 + 2000 = 5000).
        """
        self.ensure_one()
        if not self.id:
            return 0.0
        moves = self.env['stock.move'].search([
            ('product_id', '=', self.id),
            ('state', '=', 'done'),
            ('location_id.usage', 'not in', ('internal', 'transit')),
            ('location_dest_id.usage', '=', 'internal'),
        ])
        return sum(moves.mapped('quantity'))


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    bonus_qty = fields.Float(compute='_compute_bonus_figures', string="Given away")
    bonus_print_run = fields.Float(compute='_compute_bonus_figures', string="Print run")
    bonus_pct = fields.Float(compute='_compute_bonus_figures', string="% donated")
    bonus_cost = fields.Float(compute='_compute_bonus_figures', string="Bonus cost")

    def _compute_bonus_figures(self):
        for rec in self:
            variants = rec.product_variant_ids
            lines = self.env['product.bonus.line'].search([
                ('product_id', 'in', variants.ids),
                ('bonus_id.state', 'in', ('sent', 'arrived', 'closed', 'lost')),
            ])
            rec.bonus_qty = sum(lines.mapped('quantity'))
            rec.bonus_cost = sum(lines.mapped('subtotal'))
            run = sum(v._bonus_print_run() for v in variants)
            rec.bonus_print_run = run
            rec.bonus_pct = (rec.bonus_qty / run * 100.0) if run else 0.0
