# -*- coding: utf-8 -*-
from odoo import api, fields, models

# The three buckets. A reason is fine-grained ("press", "influencer",
# "launch"); a bucket is where the quota is locked and where the money comes
# from. Author copies are NOT a marketing expense: the contract created them,
# so they are a cost of the title. Mixing them would make marketing pay for a
# book it never asked for, and would under-value the title's cost.
BUCKETS = [
    ('editorial', 'Author / Editorial'),
    ('marketing', 'Marketing'),
    ('commercial', 'Commercial'),
]


class ProductBonusReason(models.Model):
    _name = 'product.bonus.reason'
    _description = 'Bonus Reason'
    _order = 'bucket, sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    bucket = fields.Selection(
        BUCKETS, required=True, default='marketing', string="Investment",
        help="Which budget pays for it (the investment), and which quota it "
             "consumes.")
    requires_approval = fields.Boolean(
        string="Requires approval", default=True,
        help="Author copies do not: the contract approved them when it was "
             "signed. Everything else does.")
    consumes_contract = fields.Boolean(
        string="Consumes contract copies",
        help="Counts against the author copies owed by the contract.")

    # A single return window would be a quiet disaster: an influencer posts in
    # a week or never, a newspaper critic takes three months. With one window
    # the critic ages into "silence" and the house stops sending books to the
    # Estadao -- a well-meaning rule destroying the most valuable thing the
    # publisher has. So the clock belongs to the reason.
    return_window_days = fields.Integer(
        string="Return window (days)", default=60,
        help="How long to wait before calling it silence. Influencer ~21, "
             "press ~120. Nobody is judged before their window closes.")

    bonus_count = fields.Integer(compute='_compute_bonus_count')

    @api.depends('name')
    def _compute_bonus_count(self):
        data = self.env['product.bonus']._read_group(
            [('reason_id', 'in', self.ids)], ['reason_id'], ['__count'])
        mapped = {reason.id: count for reason, count in data}
        for rec in self:
            rec.bonus_count = mapped.get(rec.id, 0)
