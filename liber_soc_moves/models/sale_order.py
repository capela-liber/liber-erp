# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """Consignment Pedido = a sale.order flagged is_consignment.

    Same model and same flow as a real sale (the team already knows it), but it
    is NOT a sale: it gets the "C" code instead of "S", is kept out of the Sales
    app / Sales Analysis by domains, and only becomes revenue at the Acerto.
    """
    _inherit = 'sale.order'

    is_consignment = fields.Boolean(
        string='Consignment Order', default=False, copy=False, index=True,
        help="Consignment order (Pedido C). Follows the sale flow but is not a "
             "sale: excluded from Sales reporting; revenue only at the Acerto.")
    consignment_type = fields.Selection([
        ('opening', 'Consignment Opening'),
        ('replenishment', 'Replenishment'),
    ], string='Consignment Type', copy=False,
        help="Opening = first placement of stock, created directly (no map "
             "needed). Replenishment = a refill fired by a consignment operation "
             "(CO) after the map. A Pedido created by hand can only be an opening.")
    consignment_agreement_id = fields.Many2one(
        'consignment.agreement', string='Consignment Agreement',
        compute='_compute_consignment_agreement_id', store=True, readonly=True,
        help="Resolved from the customer (one agreement per customer).")

    @api.depends('partner_id', 'company_id', 'is_consignment')
    def _compute_consignment_agreement_id(self):
        Agreement = self.env['consignment.agreement']
        for order in self:
            if order.is_consignment and order.partner_id:
                order.consignment_agreement_id = Agreement._resolve_for(
                    order.partner_id.commercial_partner_id, order.company_id)
            else:
                order.consignment_agreement_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_consignment') and vals.get('name', _('New')) in (
                    False, '/', _('New')):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sale.order.consignment') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # A Pedido C does not invoice
    # ------------------------------------------------------------------
    # Consignment is not a sale: the book on the customer's shelf is still ours, and
    # it becomes revenue at the Acerto -- which issues the fiscal note (CFOP 5113/6113)
    # and the invoice. Invoicing the Pedido would book revenue for goods nobody bought
    # yet, and it would do it twice: once here, once at the settlement.
    def _get_invoiceable_lines(self, final=False):
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(lambda l: not l.order_id.is_consignment)

    def _create_invoices(self, grouped=False, final=False, date=None):
        consignacao = self.filtered('is_consignment')
        if consignacao:
            raise UserError(_(
                "A consignment order does not invoice: %(orders)s.\n\n"
                "The books are still ours, on the customer's shelf. They become "
                "revenue at the Acerto -- which is what issues the note and the "
                "invoice, for what was actually sold.",
                orders=", ".join(consignacao.mapped('name')),
            ))
        return super()._create_invoices(grouped=grouped, final=final, date=date)

    @api.depends('is_consignment')
    def _compute_invoice_status(self):
        super()._compute_invoice_status()
        # Nothing to invoice, ever: the button and the "to invoice" lists leave it alone.
        self.filtered('is_consignment').invoice_status = 'no'
