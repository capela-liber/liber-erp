# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # O EIXO DE LEITURA que os relatórios agrupam de verdade: a rede quando a
    # ficha tem uma, o próprio cliente quando não. Agrupar pelo Many2one cru
    # despejava todo cliente sem rede num balde "Nenhum" -- 18 mil unidades
    # num único rótulo mudo, no primeiro pivô aberto. Ninguém é "Nenhum":
    # quem não é rede é ele mesmo. Um contato-pessoa sobe para a empresa em
    # que está pendurado (commercial_partner_id), senão cada comprador do
    # site viraria uma linha própria separada da loja que o atende.
    #
    # Char STORED de propósito: vira coluna física em res_partner, e o
    # sale.report a lê direto no SELECT, sem JOIN novo.
    commercial_group_display = fields.Char(
        string="Group / Client",
        compute='_compute_commercial_group_display', store=True, index=True,
        help="What reports group by: the commercial group when the record "
             "belongs to one, the client itself otherwise. Nobody lands in "
             "an anonymous 'None' bucket.")

    @api.depends('name', 'partner_group_id.name', 'commercial_partner_id.name',
                 'commercial_partner_id.partner_group_id.name')
    def _compute_commercial_group_display(self):
        for partner in self:
            top = partner.commercial_partner_id or partner
            partner.commercial_group_display = (
                top.partner_group_id.name or top.name or partner.name)

    # A REDE, não a filial: "Travessa", enquanto a ficha é a Travessa
    # Botafogo. Eixo de LEITURA -- relatórios agrupam por ele; nenhum
    # documento fiscal, contrato ou prateleira o consulta. Computado com
    # `readonly=False`, no padrão da casa (`nfe_numero`): a raiz do CNPJ
    # sugere quando o campo está vazio, e uma escolha feita à mão nunca é
    # desfeita pela sugestão -- é o que permite montar a Leitura (franquia,
    # uma raiz por loja) manualmente sem briga com o compute.
    partner_group_id = fields.Many2one(
        'liber.partner.group', string="Commercial Group",
        compute='_compute_partner_group_id', store=True, readonly=False,
        index='btree_not_null', tracking=True,
        help="The network this store belongs to -- the axis reports group "
             "by. Suggested from the CNPJ root when empty; setting it by "
             "hand always wins. Fiscal documents never read it.")

    @api.depends('vat_digits')
    def _compute_partner_group_id(self):
        for partner in self:
            if partner.partner_group_id:
                continue
            partner.partner_group_id = \
                self.env['liber.partner.group']._group_for_vat(partner.vat_digits)
