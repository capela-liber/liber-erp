# -*- coding: utf-8 -*-
from odoo import fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Consignment gets its OWN warehouse operation types, separate from the
    # sales delivery types -- a consignment return is a "retorno de mercadoria",
    # not a generic internal transfer, and keeping them apart lets the warehouse
    # prioritise sales over consignment. Auto-created on first use; parametrised
    # in Settings.
    consignment_shipment_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Consignment Shipment Operation',
        domain="[('code', '=', 'internal')]",
        help="Warehouse operation type used for consignment shipments/replenishments "
             "(warehouse -> customer shelf).")
    consignment_return_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Consignment Return Operation',
        domain="[('code', '=', 'internal')]",
        help="Warehouse operation type used for consignment returns "
             "(customer shelf -> warehouse). It is a merchandise return, not a "
             "generic internal transfer.")
    consignment_delivery_operation_type_id = fields.Many2one(
        'stock.picking.type', string='Consignment Delivery Operation',
        domain="[('code', '=', 'outgoing')]",
        help="Warehouse operation type for Pedido C deliveries (warehouse -> "
             "customer). A consignment remessa on the generic Delivery Orders "
             "reads as a sale somebody forgot to invoice; it is not. Shares "
             "the COM/ numbering with the shelf flows.")

    def _consignment_warehouse(self):
        self.ensure_one()
        return self.env['stock.warehouse'].search(
            [('company_id', '=', self.id)], limit=1)

    def _create_consignment_operation_type(self, name, prefix, seq_name,
                                            code='internal'):
        self.ensure_one()
        warehouse = self._consignment_warehouse()
        seq = self.env['ir.sequence'].sudo().create({
            'name': seq_name,
            'prefix': prefix,
            'padding': 5,
            'company_id': self.id,
        })
        return self.env['stock.picking.type'].sudo().create({
            'name': name,
            'code': code,
            'sequence_id': seq.id,
            'sequence_code': prefix.split('/')[0],
            'warehouse_id': warehouse.id if warehouse else False,
            'company_id': self.id,
        })

    def _get_consignment_delivery_operation_type(self):
        """The OUTGOING consignment operation -- what a Pedido C ships on.

        He caught it on the screen: C00003's delivery came out WH/OUT, on the
        warehouse's generic "Pedidos de entrega". A consignment remessa is not
        a sale delivery -- it needs its own operation type. It shares the COM/
        sequence with the internal shelf flows: one prefix for consignment
        logistics, as he named it ("COM, ligado a consig em logística").
        """
        self.ensure_one()
        if not self.consignment_delivery_operation_type_id:
            shipment = self._get_consignment_shipment_operation_type()
            warehouse = self._consignment_warehouse()
            self.consignment_delivery_operation_type_id = \
                self.env['stock.picking.type'].sudo().create({
                    'name': _('Consignment Delivery'),
                    'code': 'outgoing',
                    'sequence_id': shipment.sequence_id.id,  # same COM/ numbering
                    'sequence_code': 'COM',
                    'warehouse_id': warehouse.id if warehouse else False,
                    'company_id': self.id,
                })
        return self.consignment_delivery_operation_type_id

    def _get_consignment_shipment_operation_type(self):
        self.ensure_one()
        if not self.consignment_shipment_operation_type_id:
            self.consignment_shipment_operation_type_id = \
                self._create_consignment_operation_type(
                    # COM/, não mais REM/: o REM/ agora é do documento FISCAL
                    # de remessa (nfe_remessa) — dois documentos de naturezas
                    # diferentes não podem dividir um prefixo. Bases antigas
                    # precisam de UPDATE em ir_sequence + sequence_code.
                    _('Consignment Shipment'), 'COM/%(year)s/',
                    'Consignment Shipment Operation')
        return self.consignment_shipment_operation_type_id

    def _get_consignment_return_operation_type(self):
        self.ensure_one()
        if not self.consignment_return_operation_type_id:
            self.consignment_return_operation_type_id = \
                self._create_consignment_operation_type(
                    _('Consignment Return'), 'RET/%(year)s/',
                    'Consignment Return Operation')
        return self.consignment_return_operation_type_id
