# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .bonus_reason import BUCKETS

# "Se fiz 3000 e quero doar x%": the number he thinks in is a PERCENTAGE of the
# print run. The count of copies is the consequence, not the input.
DEFAULT_PCT = 5.0
DEFAULT_SPLIT = {'editorial': 25.0, 'marketing': 60.0, 'commercial': 15.0}


class ProductBonusQuota(models.Model):
    """What we ALLOW ourselves to give away, per title and bucket.

    The print run is not a record here -- it IS the stock ("a tiragem e o
    estoque"). What needed modelling was never the print run: it was the quota.

    A quota row is an OVERRIDE. Without one, the title falls back to the house
    default in Definições, so every book has a meta from day one and nobody has
    to remember to create three rows per title.
    """
    _name = 'product.bonus.quota'
    _description = 'Bonus Quota'
    _order = 'product_id, bucket'
    _rec_name = 'display_name'

    product_id = fields.Many2one(
        'product.product', string="Title", required=True,
        domain=[('type', '=', 'consu')], ondelete='cascade', index=True)
    bucket = fields.Selection(BUCKETS, required=True, default='marketing')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda s: s.env.company)

    # The percentage is what he sets; the copies are what follow.
    pct_allowed = fields.Float(
        string="% of print run", required=True, default=5.0,
        help="How much of the print run this bucket may give away. The copies "
             "are computed from it, so a reprint widens the allowance on its own.")
    qty_allowed = fields.Float(compute='_compute_figures', string="Allowed copies")
    print_run = fields.Float(
        compute='_compute_figures', string="Print run",
        help="Sum of what came INTO stock -- not the balance on hand. Stock is "
             "a moving number; a print run of 3000 stays 3000 forever.")
    qty_given = fields.Float(compute='_compute_figures', string="Given")
    qty_remaining = fields.Float(compute='_compute_figures', string="Left")
    pct_given = fields.Float(compute='_compute_figures', string="% donated")

    _product_bucket_uniq = models.Constraint(
        'unique(product_id, bucket, company_id)',
        'One quota per title and bucket.')

    @api.depends('pct_allowed', 'product_id', 'bucket')
    def _compute_figures(self):
        for rec in self:
            f = self._figures_for(rec.product_id, rec.bucket, rec.company_id)
            rec.print_run = f['run']
            rec.qty_allowed = f['allowed']
            rec.qty_given = f['given']
            rec.qty_remaining = f['left']
            rec.pct_given = f['pct_given']

    @api.model
    def _figures_for(self, product, bucket, company=None):
        """The single place that answers "how much may we still give away?".

        Both the quota screen and the live counter on the dispatch read this, so
        the number on the triage bar and the number that blocks the send can
        never disagree.
        """
        company = company or self.env.company
        empty = {'run': 0.0, 'allowed': 0.0, 'given': 0.0, 'left': 0.0,
                 'pct': 0.0, 'pct_given': 0.0}
        if not product or not bucket:
            return empty
        run = product._bonus_print_run()
        quota = self.search([
            ('product_id', '=', product.id), ('bucket', '=', bucket),
            ('company_id', '=', company.id)], limit=1)
        pct = quota.pct_allowed if quota else self._house_pct(bucket)
        allowed = run * pct / 100.0
        lines = self.env['product.bonus.line'].search([
            ('product_id', '=', product.id),
            ('bonus_id.bucket', '=', bucket),
            ('bonus_id.company_id', '=', company.id),
            ('bonus_id.state', 'in', ('sent', 'arrived', 'closed', 'lost')),
        ])
        given = sum(lines.mapped('quantity'))
        return {
            'run': run, 'allowed': allowed, 'given': given,
            'left': max(0.0, allowed - given), 'pct': pct,
            'pct_given': (given / run * 100.0) if run else 0.0,
        }

    @api.model
    def _house_pct(self, bucket):
        """The fallback: what Definições says, so a title with no quota row
        still has a meta."""
        get = self.env['ir.config_parameter'].sudo().get_param
        try:
            return float(get('product_bonus.pct_%s' % bucket,
                             DEFAULT_SPLIT.get(bucket, DEFAULT_PCT)))
        except (TypeError, ValueError):
            return DEFAULT_SPLIT.get(bucket, DEFAULT_PCT)

    @api.depends('product_id', 'bucket')
    def _compute_display_name(self):
        labels = dict(BUCKETS)
        for rec in self:
            rec.display_name = "%s / %s" % (
                rec.product_id.display_name or '?', labels.get(rec.bucket, ''))
