# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # O CANAL comercial do cliente: livrarias pequenas, distribuidoras, site
    # próprio, sebo. É o nome que o resto da casa já usa -- `Sales Channel` em
    # `consignment.template`, `consignment.shortfall`, `consignment.coverage` e
    # `stock.quant` -- e aponta para o mesmo `crm.team` que `sale.order.team_id`
    # e `account_move.team_id` carimbam. São 55.656 documentos no merge_02
    # falando esse vocabulário; um só é melhor do que dois.
    #
    # O Odoo 19 tirou `team_id` de res.partner, e o que ele tirou foi a
    # DEDUÇÃO da equipe a partir do cliente: hoje `sale.order._default_team_id`
    # não consulta mais o parceiro, e a equipe sai da filiação do vendedor
    # (`crm.team.member`). Isso pressupõe divisão por QUEM VENDE. A nossa é por
    # O QUE O CLIENTE É -- uma vendedora sozinha cobre 13 canais entre 327
    # clientes --, e nenhum arranjo de equipes-de-gente reproduz isso. Gravar o
    # canal na ficha não contradiz o 19: não deduzimos nada, e sem CRM
    # instalado `crm.team` é uma taxonomia inerte.
    #
    # `company_dependent` de propósito. No Odoo 15 este vínculo morava em
    # `ir.property`, ou seja, já era por empresa -- e num grupo com mais de uma
    # editora o mesmo cliente pode ser de canais diferentes em cada uma. São
    # 233 fichas assim no merge_02.
    team_id = fields.Many2one(
        'crm.team', string='Sales Channel', company_dependent=True,
        help="The commercial channel this customer is served through. It is "
             "the default for their documents. In consignment the agreement "
             "wins: this field is where the agreement is born, not the "
             "other way around.")
