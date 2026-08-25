# -*- coding: utf-8 -*-
from odoo import models


class StockRule(models.Model):
    """A remessa do Pedido C sai no tipo de operação da consignação -- e para
    a PRATELEIRA do cliente, não para "Clientes".

    Duas coisas, achadas em momentos diferentes, no mesmo lugar do código.

    A primeira foi o tipo de operação. A cadeia de regras do sale-stock carimba
    o tipo genérico de saída do armazém (WH/OUT, "Pedidos de entrega") em toda
    entrega que ela gera. Numa consignação isso erra duas vezes: a
    transferência parece uma entrega de venda para quem trabalha no depósito, e
    o número dela não diz nada sobre consignação. Ele pegou no WH/OUT/00006 do
    C00003.

    A segunda é o destino, e é mais grave (24/08/2026). O destino continuava
    sendo "Clientes" -- a localização de saída do core, onde o livro deixa de
    ser nosso. Só que consignação é exatamente o contrário: o livro fica nosso,
    parado na prateleira do cliente, até o acerto. Validada a remessa, o livro
    sumia do estoque e não aparecia em prateleira nenhuma; `on_shelf_qty` ficava
    zerado, o mapa mensal saía vazio e o acerto não tinha o que cobrar. No prod
    já eram 64 movimentos validados assim quando a equipe percebeu -- a
    prateleira só tinha o que a migração tinha posto lá.

    O destino certo é a localização do contrato, que nasce na ativação
    (`consignment.agreement.location_id`): interna, porque a mercadoria ainda é
    da casa, e por cliente, porque a prateleira é de um cliente só. É a mesma
    localização para onde o COM/MOV já mandava, e de onde o acerto e o CR já
    tiravam: o Pedido C era a única ponta que não falava com ela.

    Só o passo de SAÍDA muda: num armazém de várias etapas as pernas de
    separação/embalagem ficam nos tipos delas. E, com a trava do
    `sale.order.action_confirm` (contrato ativo, senão não confirma), quando
    esta linha roda a prateleira sempre existe -- o `if` de baixo é cinto de
    segurança, não caminho previsto.
    """
    _inherit = 'stock.rule'

    def _get_stock_move_values(self, product_id, product_qty, product_uom,
                               location_dest_id, name, origin, company_id,
                               values):
        vals = super()._get_stock_move_values(
            product_id, product_qty, product_uom, location_dest_id, name,
            origin, company_id, values)
        # v19: the sale reaches the rule as values['sale_line_id'] (the
        # procurement group has no sale_id here).
        line_id = values.get('sale_line_id')
        sale = (self.env['sale.order.line'].browse(line_id).order_id
                if line_id else False)
        if not (sale and sale.is_consignment and vals.get('picking_type_id')):
            return vals
        ptype = self.env['stock.picking.type'].browse(vals['picking_type_id'])
        if ptype.code != 'outgoing':
            return vals
        delivery_type = company_id._get_consignment_delivery_operation_type()
        if delivery_type:
            vals['picking_type_id'] = delivery_type.id
        shelf = sale.consignment_agreement_id.location_id
        if shelf:
            # Os DOIS: `location_dest_id` é o destino desta perna e
            # `location_final_id` é onde a cadeia termina. Mandar só o primeiro
            # não bastava -- o compute do core relê o destino do picking assim
            # que o movimento é encaixado nele (`_assign_picking`), e o picking
            # nasce justamente com o `location_dest_id` do movimento. Com os
            # dois iguais, o encaixe devolve a prateleira e nada é reescrito
            # por baixo; e o domínio de busca do encaixe inclui o destino, de
            # modo que prateleiras de clientes diferentes nunca caem na mesma
            # transferência.
            vals['location_dest_id'] = shelf.id
            vals['location_final_id'] = shelf.id
        return vals
