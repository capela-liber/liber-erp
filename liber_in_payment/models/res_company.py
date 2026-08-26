from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    use_in_payment_state = fields.Boolean(
        string="Invoices wait for bank reconciliation",
        default=True,
        help="When a payment is registered, the invoice shows In Payment "
             "and only becomes Paid once the payment is reconciled with a "
             "bank statement. Disable to mark invoices Paid immediately, "
             "as Odoo Community does by default.",
    )
