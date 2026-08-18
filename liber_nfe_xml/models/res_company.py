# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    """O padrão fiscal da VENDA — o caso comum, e por isso o mais esquecido.

    A casa já parametriza as operações especiais: a consignação declara as
    dela (remessa, acerto, devolução) no `liber_soc_fiscal_br`. Mas essas são
    exceções, e viviam num módulo que nem toda instalação tem: sem o SOC, não
    havia lugar nenhum para dizer qual é a posição fiscal de uma venda comum.

    Então ela mora aqui, na raiz da família fiscal (todo o resto -- Olist,
    Focus, SOC, influencers -- depende deste módulo). Quem vende sem
    consignação, sem marketplace e sem Focus continua tendo onde declarar o
    padrão da casa; quem tem as operações especiais sobrepõe cada uma no seu
    módulo, exatamente como já faz.

    Vazio, nada acontece: o Odoo segue derivando da ficha do cliente, que é o
    comportamento de sempre.
    """
    _inherit = 'res.company'

    sale_fiscal_position_id = fields.Many2one(
        'account.fiscal.position', string='Sale — Fiscal Position',
        help="Fiscal position for an ordinary sale, when no special operation "
             "says otherwise. Consignment, bonus and event shipments declare "
             "their own; this is the house default for selling.")
