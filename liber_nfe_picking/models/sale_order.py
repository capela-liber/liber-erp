# -*- coding: utf-8 -*-
from odoo import api, fields, models

from odoo.addons.liber_nfe_focus.models.res_partner import MODALIDADE_FRETE


class SaleOrder(models.Model):
    """O pedido carrega quem paga o frete.

    A modalidade nasce no cadastro do cliente (padrão comercial) e desce
    para cá quando o cliente é escolhido -- mas fica editável, porque frete
    se negocia por pedido. Da fatura ela segue para a NFe.
    """
    _inherit = 'sale.order'

    nfe_modalidade_frete = fields.Selection(
        selection=MODALIDADE_FRETE, string='Modalidade do frete',
        compute='_compute_nfe_modalidade_frete', store=True, readonly=False,
        help="Quem contrata o transporte desta venda. Vem do cadastro do "
             "cliente e pode mudar aqui, caso a caso. Vazio, a nota sai no "
             "padrão da casa: CIF, o remetente contrata.")

    @api.depends('partner_id')
    def _compute_nfe_modalidade_frete(self):
        """O padrão do cliente entra quando ele tem um; senão fica como está.

        Não zera o que foi digitado quando o novo cliente não tem padrão:
        trocar o destinatário não apaga a negociação de frete já feita.
        """
        for order in self:
            padrao = (order.partner_id.commercial_partner_id
                      .nfe_modalidade_frete)
            order.nfe_modalidade_frete = padrao or order.nfe_modalidade_frete
