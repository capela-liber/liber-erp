# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ConsignmentAgreement(models.Model):
    _inherit = 'consignment.agreement'

    move_ids = fields.One2many('consignment.move', 'agreement_id', string='Movements')
    move_count = fields.Integer(string='# Movements', compute='_compute_move_count')

    def _compute_move_count(self):
        groups = self.env['consignment.move']._read_group(
            [('agreement_id', 'in', self.ids)], ['agreement_id'], ['__count'])
        counts = {agreement.id: count for agreement, count in groups}
        for agr in self:
            agr.move_count = counts.get(agr.id, 0)

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Movements'),
            'res_model': 'consignment.move',
            'view_mode': 'list,form',
            'domain': [('agreement_id', '=', self.id)],
            'context': {'default_agreement_id': self.id},
        }

    order_count = fields.Integer(string='# Orders', compute='_compute_order_count')

    def _compute_order_count(self):
        groups = self.env['sale.order']._read_group(
            [('consignment_agreement_id', 'in', self.ids)],
            ['consignment_agreement_id'], ['__count'])
        counts = {agr.id: count for agr, count in groups}
        for agr in self:
            agr.order_count = counts.get(agr.id, 0)

    def action_view_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Orders'),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('consignment_agreement_id', '=', self.id)],
            'context': {'default_is_consignment': True,
                        'default_partner_id': self.partner_id.id},
        }

    # ------------------------------------------------------------------
    # Whole-shelf actions (belong to the relationship, not a periodic op)
    # ------------------------------------------------------------------
    def _open_move(self, move, name):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'consignment.move',
            'view_mode': 'form',
            'res_id': move.id,
        }

    def action_recall_all(self):
        """Total return: recall the entire shelf. Precondition for closing.

        The whole current map comes back to the warehouse as one return
        movement (pure stock, never a sale). Once the warehouse processes it and
        the shelf is empty, the agreement can be closed.
        """
        self.ensure_one()
        if self.state not in ('active', 'suspended'):
            raise UserError(_("Only an active or suspended agreement can be recalled."))
        quants = self.env['stock.quant'].search([
            ('location_id', '=', self.location_id.id), ('quantity', '>', 0)])
        if not quants:
            raise UserError(_("The shelf is already empty; nothing to recall."))
        aggregated = {}
        for quant in quants:
            aggregated.setdefault(quant.product_id, 0.0)
            aggregated[quant.product_id] += quant.quantity
        move = self.env['consignment.move'].create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'move_kind': 'return',
            'note': _("Total recall for agreement %s (closing).") % self.name,
            'line_ids': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': qty,
                'product_uom': product.uom_id.id,
            }) for product, qty in aggregated.items()],
        })
        return self._open_move(move, _('Total Recall'))

    def action_symbolic_renewal(self):
        """Renew the fiscal clock over the whole shelf (note-only, no goods)."""
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_("Only an active agreement can be renewed."))
        move = self.env['consignment.move'].create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'move_kind': 'symbolic_renewal',
            'note': _("Symbolic renewal for agreement %s (fiscal clock).") % self.name,
        })
        move.action_confirm()
        return self._open_move(move, _('Symbolic Renewal'))
