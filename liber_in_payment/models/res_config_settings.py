from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    use_in_payment_state = fields.Boolean(
        related='company_id.use_in_payment_state', readonly=False)
