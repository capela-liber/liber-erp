# -*- coding: utf-8 -*-
from odoo import fields, models


class ConsignmentSettlementStage(models.Model):
    """Kanban stage for the consignment operation (CO) work board.

    The CO is where the monthly work happens (chasing settlements, replenishments,
    returns) -- almost a CRM. These stages are the kanban columns (A Fazer /
    Fazendo / Feito); being records, the team reconfigures the columns itself
    (rename/reorder/fold, add new ones) without touching code.
    """
    _name = 'consignment.settlement.stage'
    _description = 'Consignment Settlement Stage'
    _order = 'sequence, id'

    name = fields.Char(string='Stage', required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(
        string='Folded in Kanban',
        help="Fold this column in the kanban when it has no records to show "
             "(typical for a terminal stage like 'Feito').")
