# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConsignmentMove(models.Model):
    """Add the ``adjustment`` kind: a count correction on the shelf.

    Unlike shipment/replenishment/return (which relocate stock between our
    warehouse and the customer shelf, the goods staying ours), an adjustment
    reconciles the *book* shelf balance (the map) with the *fiscal* truth
    rebuilt by the audit. It has two sides:

    - quantity: a real inventory movement between the shelf and an
      inventory-usage location, so the correction lives in the stock history;
    - value: a journal entry between the Consignment Adjustment account and the
      Consignment Stock account (115000, soc_fiscal_br).

    The quantity move is intentionally *not* valued (both endpoints are
    non-valued in this fork), so the value is posted explicitly and stays
    correct regardless of the product's valuation method.
    """
    _inherit = 'consignment.move'

    move_kind = fields.Selection(
        selection_add=[('adjustment', 'Adjustment')],
        ondelete={'adjustment': 'cascade'})
    audit_id = fields.Many2one(
        'consignment.audit', string='Audit', copy=False, index=True,
        help="The audit that generated this adjustment.")
    account_move_id = fields.Many2one(
        'account.move', string='Value Entry', copy=False, readonly=True,
        help="Journal entry that posted the value of an adjustment.")

    @api.depends('move_kind')
    def _compute_is_physical(self):
        super()._compute_is_physical()
        for mv in self:
            if mv.move_kind == 'adjustment':
                mv.is_physical = True

    def action_confirm(self):
        adjustments = self.filtered(lambda m: m.move_kind == 'adjustment')
        res = super(ConsignmentMove, self - adjustments).action_confirm()
        for mv in adjustments:
            if mv.state != 'draft':
                continue
            if not mv.agreement_id:
                raise UserError(_(
                    "Customer %s has no consignment agreement.")
                    % mv.partner_id.display_name)
            if not mv.line_ids.filtered('adjustment_delta'):
                raise UserError(_("Nothing to adjust: every delta is zero."))
            mv._apply_adjustment()
            mv.state = 'done'
        return res

    def action_cancel(self):
        done_adj = self.filtered(
            lambda m: m.move_kind == 'adjustment' and m.state == 'done')
        if done_adj:
            raise UserError(_(
                "A done consignment adjustment cannot be cancelled -- it has "
                "already moved stock and posted its value. Post an opposite "
                "adjustment instead."))
        return super().action_cancel()

    # ------------------------------------------------------------------
    # Applying the adjustment (never writes stock.quant directly)
    # ------------------------------------------------------------------
    def _apply_adjustment(self):
        self.ensure_one()
        shelf = self.agreement_id.location_id
        if not shelf:
            raise UserError(_(
                "Agreement %s has no shelf. Activate it first.")
                % self.agreement_id.name)
        company = self.company_id
        adj_loc = company._get_consignment_adjustment_location()
        Move = self.env['stock.move']
        value_total = 0.0  # signed: + found stock, - shrinkage
        for line in self.line_ids:
            delta = line.adjustment_delta
            if not delta:
                continue
            if delta > 0:  # fiscal says more than the map -> found stock
                src, dest, qty = adj_loc, shelf, delta
            else:          # fiscal says less than the map -> shrinkage/loss
                src, dest, qty = shelf, adj_loc, -delta
            move = Move.create({
                'reference': self.name,
                'origin': self.name,
                'product_id': line.product_id.id,
                'product_uom_qty': qty,
                'product_uom': line.product_uom.id,
                'location_id': src.id,
                'location_dest_id': dest.id,
                'company_id': company.id,
                'is_inventory': True,
            })
            move._action_confirm()
            move._action_assign()
            move.quantity = qty
            move.picked = True
            move._action_done()
            cost = line.product_id.with_company(company).standard_price
            value_total += delta * cost
        self._post_adjustment_value(value_total)

    def _post_adjustment_value(self, value_total):
        """Post the value difference: Consignment Adjustment vs Stock (115000)."""
        self.ensure_one()
        company = self.company_id
        currency = company.currency_id
        if currency.is_zero(value_total):
            return
        loss_acc = company.consignment_adjustment_account_id
        stock_acc = company.consignment_stock_account_id
        if not loss_acc or not stock_acc:
            self.message_post(body=_(
                "Shelf quantity adjusted, but the value entry was skipped: set "
                "both the Consignment Adjustment Account and the Consignment "
                "Stock Account in Settings, then post the value manually."))
            return
        journal = company._get_consignment_adjustment_journal()
        amount = abs(value_total)
        if value_total > 0:   # found stock: asset up, gain
            debit_acc, credit_acc = stock_acc, loss_acc
        else:                 # shrinkage: loss, asset down
            debit_acc, credit_acc = loss_acc, stock_acc
        label = _("Consignment audit adjustment %s") % self.name
        entry = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': fields.Date.context_today(self),
            'ref': label,
            'move_type': 'entry',
            'company_id': company.id,
            'line_ids': [
                (0, 0, {'account_id': debit_acc.id, 'name': label,
                        'debit': amount, 'credit': 0.0}),
                (0, 0, {'account_id': credit_acc.id, 'name': label,
                        'debit': 0.0, 'credit': amount}),
            ],
        })
        entry.action_post()
        self.account_move_id = entry.id
        self.message_post(body=_(
            "Value entry %(entry)s posted: %(amt).2f (Dr %(dr)s / Cr %(cr)s).",
            entry=entry.name, amt=amount,
            dr=debit_acc.display_name, cr=credit_acc.display_name))


class ConsignmentMoveLine(models.Model):
    _inherit = 'consignment.move.line'

    adjustment_delta = fields.Integer(
        string='Adjustment',
        help="Signed shelf correction for an 'adjustment' movement: positive "
             "adds units to the shelf (found stock), negative removes them "
             "(shrinkage). Ignored for the other movement kinds.")
