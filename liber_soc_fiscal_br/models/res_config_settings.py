# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    consignment_stock_account_id = fields.Many2one(
        related='company_id.consignment_stock_account_id', readonly=False,
        string='Consignment Stock Account')

    consignment_shipment_fiscal_position_id = fields.Many2one(
        related='company_id.consignment_shipment_fiscal_position_id', readonly=False)
    consignment_shipment_cfop_in_id = fields.Many2one(
        related='company_id.consignment_shipment_cfop_in_id', readonly=False)
    consignment_shipment_cfop_out_id = fields.Many2one(
        related='company_id.consignment_shipment_cfop_out_id', readonly=False)
    consignment_sale_fiscal_position_id = fields.Many2one(
        related='company_id.consignment_sale_fiscal_position_id', readonly=False)
    consignment_sale_cfop_in_id = fields.Many2one(
        related='company_id.consignment_sale_cfop_in_id', readonly=False)
    consignment_sale_cfop_out_id = fields.Many2one(
        related='company_id.consignment_sale_cfop_out_id', readonly=False)
    consignment_return_fiscal_position_id = fields.Many2one(
        related='company_id.consignment_return_fiscal_position_id', readonly=False)
    consignment_return_cfop_in_id = fields.Many2one(
        related='company_id.consignment_return_cfop_in_id', readonly=False)
    consignment_return_cfop_out_id = fields.Many2one(
        related='company_id.consignment_return_cfop_out_id', readonly=False)
    consignment_shipment_operation_type_id = fields.Many2one(
        related='company_id.consignment_shipment_operation_type_id', readonly=False)
    consignment_return_operation_type_id = fields.Many2one(
        related='company_id.consignment_return_operation_type_id', readonly=False)

    def action_wire_consignment_shelves(self):
        self.company_id.action_wire_consignment_shelves()
        return True
