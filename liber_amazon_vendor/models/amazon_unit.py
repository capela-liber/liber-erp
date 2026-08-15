# -*- coding: utf-8 -*-
"""
A unidade da Amazon, e quem ela é no nosso cadastro.

A Amazon não compra como uma pessoa só. Cada centro de distribuição é um
estabelecimento fiscal próprio -- no Brasil, mesma raiz de CNPJ e filial
diferente -- e o pedido diz qual deles está comprando, no `buyingParty`.

O que ela **não** manda é quem é esse estabelecimento: o payload traz
`{"partyId": "GRU8"}` e mais nada. Sem endereço, sem razão social, sem
inscrição fiscal. A especificação da SP-API prevê os campos `address` e
`taxInfo`; a Amazon não os preenche.

Daí este modelo. A sigla é a única chave que atravessa a fronteira, e alguém
precisa dizer, uma vez, a quem ela corresponde aqui dentro. Adivinhar pelo
nome do parceiro funcionaria numa casa que batize os contatos de
"Amazon GRU8" -- e em nenhuma outra. Convenção de cadastro de uma editora não
serve de regra de um módulo.
"""

from odoo import api, fields, models, _


class LiberAmazonUnit(models.Model):
    _name = 'liber.amazon.unit'
    _description = 'Amazon Unit'
    _order = 'account_id, code'

    account_id = fields.Many2one(
        'liber.amazon.account', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='account_id.company_id', store=True, index=True)

    code = fields.Char(
        string='Amazon Code', required=True, index=True,
        help="The partyId Amazon sends on the order, such as GRU8. It is the "
             "only identifier of the buying establishment that crosses the "
             "API -- there is no CNPJ or address in the payload.")
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True,
        help="Who this unit is in our contacts. The quotation is made out to "
             "this partner, so its tax details are the ones that reach the "
             "invoice.")
    shipping_partner_id = fields.Many2one(
        'res.partner', string='Delivery Address',
        help="Where the books go, when it differs from the buyer. Leave empty "
             "to deliver to the customer's own address.")
    active = fields.Boolean(default=True)

    _code_account_uniq = models.Constraint(
        'unique(code, account_id)',
        'This Amazon code is already mapped for this account.')

    @api.depends('code', 'partner_id')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s — %s' % (
                record.code or '?', record.partner_id.name or _('(no customer)'))

    def _recompute_orders(self):
        """
        Manda os pedidos afetados recalcularem o cliente.

        O campo do pedido não tem como depender do mapa -- não existe
        `@api.depends` para "qualquer unidade com esta sigla". Sem este
        empurrão, mapear a unidade hoje não consertaria os pedidos que
        chegaram ontem: eles continuariam sem cliente, e ninguém entenderia
        por quê.
        """
        pedidos = self.env['liber.amazon.order'].search([
            ('account_id', 'in', self.account_id.ids),
            ('buying_party', 'in', [c for c in self.mapped('code') if c]),
        ])
        if pedidos:
            pedidos._compute_unit()

    @api.model_create_multi
    def create(self, vals_list):
        unidades = super().create(vals_list)
        unidades._recompute_orders()
        return unidades

    def write(self, vals):
        # Antes e depois: mudar a sigla desliga os pedidos antigos e liga os
        # novos, e os dois conjuntos precisam ser recalculados.
        antes = self.exists()
        antes._recompute_orders()
        res = super().write(vals)
        self.exists()._recompute_orders()
        return res

    def unlink(self):
        pedidos = self.env['liber.amazon.order'].search([
            ('unit_id', 'in', self.ids)])
        res = super().unlink()
        if pedidos:
            pedidos._compute_unit()
        return res

    @api.model
    def _resolve(self, account, code):
        """A unidade de uma sigla, ou vazio. Sem palpite."""
        if not code:
            return self.browse()
        return self.search([('account_id', '=', account.id),
                            ('code', '=', code)], limit=1)
