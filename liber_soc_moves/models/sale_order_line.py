# -*- coding: utf-8 -*-
from odoo import models


class SaleOrderLine(models.Model):
    """Na consignação, ENTREGUE quer dizer "chegou na prateleira do cliente".

    O core conta como entregue o que termina numa localização de CLIENTE, e só.
    A regra faz sentido na venda: lá, sair do armazém e deixar de ser nosso são
    o mesmo acontecimento. Na consignação são dois. O livro chega à livraria e
    continua sendo da casa -- por isso a prateleira é uma localização interna --
    e só deixa de ser nosso no acerto.

    Sem este ajuste, o desvio da remessa para a prateleira (ver stock_rule.py)
    zerava a quantidade entregue de todo Pedido C. Não é detalhe de relatório:
    é a `qty_delivered` que a nota de remessa lê para declarar o que vai dentro
    da caixa. O sintoma foi imediato e certeiro -- dez testes do
    liber_soc_fiscal_br passaram a dizer "o pedido ainda não movimentou
    mercadoria" para pedidos cuja transferência estava validada.

    O que se acrescenta é estreito de propósito: só pedidos de consignação, e
    só os movimentos que tocam a prateleira DAQUELE contrato. Ida conta como
    saída; volta -- a devolução na porta, ainda amarrada à linha do pedido --
    conta como entrada, e abate. O que sai da prateleira no acerto não passa
    por aqui: aquele movimento pertence à venda do acerto, vai para Clientes, e
    o core já o conta sozinho.
    """
    _inherit = 'sale.order.line'

    def _get_outgoing_incoming_moves(self, strict=True):
        saida, entrada = super()._get_outgoing_incoming_moves(strict=strict)
        prateleira = (self.order_id.consignment_agreement_id.location_id
                      if self.order_id.is_consignment else False)
        if not prateleira:
            return saida, entrada
        for move in self.move_ids:
            if move.state == 'cancel' or move.product_id != self.product_id:
                continue
            if move.location_dest_id == prateleira:
                # Devolvido e não estornado é o mesmo descarte que o core faz:
                # senão a ida contaria duas vezes, uma no envio e outra no
                # movimento que a desfez.
                if not move.origin_returned_move_id or move.to_refund:
                    saida |= move
            elif move.location_id == prateleira and move.to_refund:
                entrada |= move
        return saida, entrada
