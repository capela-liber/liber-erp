# -*- coding: utf-8 -*-
from odoo import _, fields, models


class ResCompany(models.Model):
    """The BON/ operation type, created on first use, per company.

    Same reasoning as soc_moves: a bonus shipment must not land in the
    warehouse's Delivery Orders. Not because it is unbilled -- in Brazil every
    movement carries an XML, a book thrown away still needs one -- but because
    the note it carries is a DIFFERENT one: a remessa (CFOP 5910), no
    receivable, against a sale's note with one. Same physical move, different
    fiscal document, and the operation type is what tells the future emission
    which CFOP to stamp.
    """
    _inherit = 'res.company'

    bonus_operation_type_id = fields.Many2one('stock.picking.type')

    # --- Bonus fiscal parametrization --------------------------------------
    # The identity of the operation lives in the FISCAL POSITION, exactly like
    # Odoo 15 production: it carries the account mapping and the auto-paid
    # pair (nfe_remessa), so the note posts as Paid with nothing owed. The
    # journal is the shared remessa journal (REM/) -- not configured here,
    # asked from nfe_remessa on first use. What remains per company is which
    # fiscal position is the bonus one, and its CFOP.
    bonus_fiscal_position_id = fields.Many2one(
        'account.fiscal.position', string="Bonus Fiscal Position",
        help="Must have Auto Invoice Paid: a bonus note never generates "
             "payment. Also carries the account mapping for the future NF-e.")
    bonus_cfop_id = fields.Many2one(
        'nfe.cfop', string="Bonus CFOP",
        domain="[('document_kind', '=', 'bonus')]",
        help="5910/6910 -- Remessa em bonificação, doação ou brinde.")

    def _bonus_fiscal_ready(self):
        self.ensure_one()
        fpos = self.bonus_fiscal_position_id
        return bool(fpos and fpos.auto_invoice_paid
                    and fpos.auto_invoice_paid_account_id)

    def _get_bonus_operation_type(self):
        self.ensure_one()
        if self.bonus_operation_type_id:
            return self.bonus_operation_type_id
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.id)], limit=1)
        if not warehouse:
            return self.env['stock.picking.type']
        sequence = self.env['ir.sequence'].sudo().create({
            'name': _("Bonus shipment (%s)", self.name),
            'prefix': 'BON/%(year)s/',
            'padding': 5,
            'company_id': self.id,
        })
        ptype = self.env['stock.picking.type'].sudo().create({
            'name': _("Bonus shipment"),
            'code': 'outgoing',
            'sequence_id': sequence.id,
            # v19 requires it even when we bring our own sequence_id (the core
            # only auto-creates one when sequence_id is absent). Same shape as
            # soc_moves: the prefix before the slash.
            'sequence_code': 'BON',
            'warehouse_id': warehouse.id,
            'company_id': self.id,
            'default_location_src_id': warehouse.lot_stock_id.id,
            'default_location_dest_id': self.env.ref(
                'stock.stock_location_customers').id,
        })
        self.sudo().bonus_operation_type_id = ptype
        return ptype
