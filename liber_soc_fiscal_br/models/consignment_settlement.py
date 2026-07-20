# -*- coding: utf-8 -*-
from odoo import models


class ConsignmentSettlement(models.Model):
    """A posição fiscal do acerto é ditada pela OPERAÇÃO, não pelo cliente.

    O Odoo deriva `sale.order.fiscal_position_id` do parceiro
    (`_compute_fiscal_position_id`, store/precompute) -- e isso resolve o eixo
    errado. `res.partner.property_account_position_id` é campo ÚNICO: a livraria
    tem uma posição fiscal só, a do regime e do estado dela. A MESMA livraria
    recebe remessa de consignação (5917) e pode comprar em firme (5102). O
    parceiro não codifica as duas.

    Sem esta sobreposição a falha é silenciosa e fiscal: o padrão do Odoo não
    deixa o campo vazio -- ele preenche com a posição fiscal de VENDA, e ninguém
    vê até a nota sair errada. Campo morto a gente descobre; valor errado, não.

    Por que aqui e não no soc_settlement: o acerto não conhece configuração
    fiscal (não depende do soc_fiscal_br). Quem depende é este módulo, e é dele
    a responsabilidade de ler o que ele mesmo declara.
    """
    _inherit = 'consignment.settlement'

    def _create_sale_order(self, sold_lines):
        order = super()._create_sale_order(sold_lines)
        fp = self.company_id.consignment_sale_fiscal_position_id
        if fp:
            # Escrever depois do create é de propósito: dispara o recálculo de
            # impostos das linhas (sale.order.line._compute_tax_id depende de
            # order_id.fiscal_position_id), que é justamente o efeito desejado.
            order.fiscal_position_id = fp
        # Empresa sem configuração cai no padrão do Odoo em vez de estourar: o
        # acerto é fluxo de operação diária e não pode parar por configuração
        # que nunca foi preenchida. Quem alerta sobre isso é a tela, não uma
        # exceção no meio do action_run.
        return order
