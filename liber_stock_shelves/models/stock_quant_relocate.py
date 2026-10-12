# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class StockQuantRelocate(models.TransientModel):
    """O Realocar também fica dentro do armazém.

    O domínio do core (interno + empresa) oferecia as prateleiras de
    consignação dos clientes como destino. Realocar é arrumação de depósito;
    o que vai para a prateleira do cliente vai pelo Pedido C.
    """
    _inherit = 'stock.quant.relocate'

    dest_location_id = fields.Many2one(
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id), "
               "('warehouse_id', '!=', False)]")

    def action_relocate_quants(self):
        for wiz in self:
            dest = wiz.dest_location_id
            if dest and (dest.usage != 'internal' or not dest.warehouse_id):
                raise UserError(_(
                    "%(location)s is not a warehouse shelf. Relocate moves "
                    "books between shelves of the warehouse; consignment "
                    "shelves are reached by their own operations.",
                    location=dest.display_name))
        return super().action_relocate_quants()
