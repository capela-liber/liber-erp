# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    """A transferência interna fica dentro do armazém (08/10/2026).

    As prateleiras de consignação (`CO/<cliente>`) são locais internos -- a
    mercadoria continua nossa na prateleira do outro -- mas moram fora da
    árvore do armazém, debaixo de um "CO" por empresa. O campo de local do
    core não tem domínio, então a Transferência interna oferecia ao depósito
    pôr livro na prateleira de um cliente sem Pedido C, remessa nem acerto.
    O dono chamou de erro grave, e é: transcende o depósito.

    A cerca vale só para o tipo INT do armazém (`warehouse.int_type_id`). Os
    tipos internos da consignação (COM/IN, COM/MOV) cruzam a fronteira de
    propósito e ficam de fora.
    """
    _inherit = 'stock.picking'

    is_shelf_transfer = fields.Boolean(
        compute='_compute_is_shelf_transfer',
        help="Internal transfer of the warehouse itself (shelf to shelf).")
    shelf_warehouse_id = fields.Many2one(
        related='picking_type_id.warehouse_id', string='Shelf Warehouse')

    @api.depends('picking_type_id')
    def _compute_is_shelf_transfer(self):
        for picking in self:
            tipo = picking.picking_type_id
            picking.is_shelf_transfer = bool(
                tipo and tipo.code == 'internal'
                and tipo.warehouse_id
                and tipo == tipo.warehouse_id.int_type_id)

    @api.constrains('location_id', 'location_dest_id', 'picking_type_id')
    def _check_shelf_transfer_inside_warehouse(self):
        for picking in self.filtered('is_shelf_transfer'):
            for local in (picking.location_id, picking.location_dest_id):
                picking._raise_if_outside_warehouse(local)

    def _raise_if_outside_warehouse(self, local):
        """Levanta se o local não é prateleira deste armazém."""
        self.ensure_one()
        armazem = self.picking_type_id.warehouse_id
        if local and (local.usage != 'internal'
                      or local.warehouse_id != armazem):
            raise ValidationError(_(
                "%(location)s is not a shelf of %(warehouse)s. An internal "
                "transfer moves books between shelves of the warehouse; "
                "consignment shelves and other locations are reached by "
                "their own operations.",
                location=local.display_name, warehouse=armazem.display_name))
