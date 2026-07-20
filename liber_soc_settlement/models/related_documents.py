# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

# Relation table shared by both sides of the NFe <-> settlement link.
_NFE_SETTLEMENT_REL = 'consignment_settlement_nfe_xml_rel'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    consignment_operation_id = fields.Many2one(
        'consignment.settlement', string='Consignment Settlement',
        copy=False, index=True, readonly=True,
        help="The consignment (acerto) that generated this sale. Set only by the "
             "operation (CO) -- a sale can never be turned into an acerto by hand "
             "in Sales.")

    @api.depends('partner_id', 'company_id', 'is_consignment', 'consignment_operation_id')
    def _compute_consignment_agreement_id(self):
        # Base resolves the agreement for the Pedido C (is_consignment). Extend it
        # so an Acerto (a real sale born from a CO) also carries its contract --
        # taken straight from the operation -- so Sales can group Acertos by
        # contract (the CO itself is one-per-acerto, useless for grouping).
        super()._compute_consignment_agreement_id()
        for order in self:
            if not order.consignment_agreement_id and order.consignment_operation_id:
                order.consignment_agreement_id = order.consignment_operation_id.agreement_id

    def action_view_consignment_operation(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consignment'),
            'res_model': 'consignment.settlement',
            'view_mode': 'form',
            'res_id': self.consignment_operation_id.id,
        }


class ConsignmentSettlement(models.Model):
    _inherit = 'consignment.settlement'

    nfe_xml_ids = fields.Many2many(
        'nfe.xml.panel', _NFE_SETTLEMENT_REL,
        'settlement_id', 'nfe_xml_id',
        string='Fiscal Documents (NFe)', copy=False,
        help="NFe documents (shipments, returns, sales) that support this "
             "settlement, for the historical audit against the map.")
    nfe_xml_count = fields.Integer(
        string='NFe Count', compute='_compute_nfe_xml_count')

    @api.depends('nfe_xml_ids')
    def _compute_nfe_xml_count(self):
        for st in self:
            st.nfe_xml_count = len(st.nfe_xml_ids)

    def action_view_nfe_xml(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fiscal Documents (NFe)'),
            'res_model': 'nfe.xml.panel',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.nfe_xml_ids.ids)],
        }


class NfeXmlPanel(models.Model):
    _inherit = 'nfe.xml.panel'

    consignment_settlement_ids = fields.Many2many(
        'consignment.settlement', _NFE_SETTLEMENT_REL,
        'nfe_xml_id', 'settlement_id',
        string='Consignments', copy=False,
        help="Consignment settlements (acertos) this fiscal document belongs "
             "to. A shipment/return can be split across settlements, so this "
             "is a many-to-many link.")
    consignment_settlement_count = fields.Integer(
        string='Consignments Count',
        compute='_compute_consignment_settlement_count')

    @api.depends('consignment_settlement_ids')
    def _compute_consignment_settlement_count(self):
        for nfe in self:
            nfe.consignment_settlement_count = len(nfe.consignment_settlement_ids)

    def action_view_consignment_settlements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consignments'),
            'res_model': 'consignment.settlement',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.consignment_settlement_ids.ids)],
        }


class ConsignmentMove(models.Model):
    _inherit = 'consignment.move'

    consignment_operation_id = fields.Many2one(
        'consignment.settlement', string='Consignment',
        copy=False, index=True,
        help="The consignment (acerto) that generated this movement.")

    def action_view_consignment_operation(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consignment'),
            'res_model': 'consignment.settlement',
            'view_mode': 'form',
            'res_id': self.consignment_operation_id.id,
        }
