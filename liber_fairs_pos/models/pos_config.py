# -*- coding: utf-8 -*-
"""O caixa sabe de que feira ele é."""
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # O caixa é DE ALGUÉM. Sem este vínculo, quem tem o papel de PDV vê
    # todos os caixas da casa -- a loja, a padaria, o caixa da colega -- e a
    # pessoa contratada para três dias de feira abre a tela numa lista que
    # não é dela.
    fair_cashier_id = fields.Many2one(
        'event.fair.cashier', string='Operator', ondelete='set null',
        index=True, copy=False)

    # O percentual VIAJA para o balcão junto com a configuração: é com ele
    # que o cartão mostra "de R$ 100 por R$ 50". Fazer a conta no cliente com
    # o preço cheio é o mesmo número que a lista de preços aplica, e não
    # depende das entranhas de precificação do PDV.
    fair_discount_pc = fields.Float(
        related='fair_id.discount_pc', store=True, readonly=True,
        string='Fair discount (%)')

    fair_id = fields.Many2one(
        # Mesmo motivo do tipo de operação: o caixa guarda venda, e venda
        # não se apaga porque o registro da feira foi apagado.
        'event.fair', string='Fair', ondelete='set null', index=True,
        help="The fair this register belongs to. It sells from that fair's "
             "table, not from the warehouse.")

    # NÃO se sobrescreve `_load_pos_data_fields` aqui. Para o `pos.config` a
    # lista vazia significa TODOS OS CAMPOS (o núcleo faz `read([])`), e
    # acrescentar um nome à lista vira "leia só este" -- o caixa morre no
    # `use_pricelist` que o próprio núcleo lê depois. Como `fair_discount_pc`
    # é gravado, ele já viaja sozinho.
