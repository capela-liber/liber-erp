# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # O documento passa a falar a língua da casa. O campo é o MESMO do núcleo
    # -- mesma coluna, mesmo `crm.team`, mesma `check_company` --; muda só o
    # rótulo, porque aqui `crm.team` é canal de clientela e não time de gente.
    #
    # Não é invenção nossa: nos próprios filtros do Odoo o nome técnico deste
    # agrupamento é `sales_channel` (`sale/views/account_views.xml`,
    # `sale/report/sale_report_views.xml`). "Canal" é o vocabulário antigo da
    # Odoo, que sobreviveu nos nomes técnicos depois que o rótulo virou "team".
    team_id = fields.Many2one(string='Sales Channel')


class AccountMove(models.Model):
    _inherit = 'account.move'

    # `account.move.team_id` é do módulo `sale` (sale/models/account_move.py),
    # não do `account` -- por isso a dependência deste módulo é `sale`.
    team_id = fields.Many2one(string='Sales Channel')
