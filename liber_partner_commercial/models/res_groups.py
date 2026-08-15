# -*- coding: utf-8 -*-
"""O desconto é um número, não um preço menor.

Com a opção "Descontos" desligada -- o padrão do Odoo --, o percentual da lista
de preços entra DENTRO do preço unitário e o campo Desc.% fica em zero: um
livro de 54,90 numa lista de 55% sai por 24,705, Desc. 0. O total fecha, e o
desconto some do razão.

O que some com ele:

- o **royalty sobre o preço de venda** tem por base `preço x quantidade`
  (`liber_copyright_contracts_analytics`). Com o preço já líquido, o autor
  passa a receber sobre 24,705 em vez de 54,90;
- a **venda especial** só é reconhecida quando `invoice_line_ids.discount`
  alcança o mínimo configurado -- com desconto zero, nenhuma alcança;
- o **vDesc da NFe** sai da diferença entre o bruto e o subtotal
  (`liber_nfe_focus`), e um preço já líquido a zera: o DANFE vai sem desconto.

POR QUE AQUI. A decisão nasceu no `edlab_stack`, onde mora o que é gosto da
casa, e mudou de casa em 09/08/2026: os três que dependem dela são módulos
`liber_` do produto aberto, e o interruptor ficava num módulo privado. Quem
instalasse o Liber receberia royalty calculado sobre preço líquido, em
silêncio. O que é gosto (quais colunas a tela abre mostrando) ficou lá; o que
é condição para o produto funcionar veio para cá.

Ligada, o Odoo devolve o preço de tabela ao `price_unit` e o percentual ao
`discount`, nos Pedidos C e S (a coluna do core já tem `groups=`) e na fatura.

Roda por `<function>` e não por `<record>`: mexer em `implied_ids` de um grupo
do `base` por XML carimbaria o `noupdate` do registro alheio. Aqui é uma
escrita idempotente, que todo `-u liber_partner_commercial` reaplica.
"""

from odoo import api, models

FEATURE = 'sale.group_discount_per_so_line'


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _liber_ligar_desconto_por_linha(self):
        desconto = self.env.ref(FEATURE, raise_if_not_found=False)
        interno = self.env.ref('base.group_user', raise_if_not_found=False)
        if not (desconto and interno):
            return
        if desconto not in interno.implied_ids:
            interno.sudo().implied_ids = [(4, desconto.id)]
