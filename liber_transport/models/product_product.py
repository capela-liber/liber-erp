# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductProduct(models.Model):
    """Cadastrar o peso do livro tem de chegar às entregas que ainda vão sair.

    O peso do movimento (``stock.move.weight``, do ``stock_delivery``) é
    ARMAZENADO e só se refaz quando a linha muda — produto, quantidade,
    unidade. O peso do produto não está nessas dependências, de propósito:
    para o Odoo, o que foi despachado pesou o que pesava naquele dia.

    Só que isso vale para o que já saiu. Para a entrega que ainda está na
    bancada, o peso velho é mentira — e era o que acontecia aqui: cadastrava-se
    o peso do livro, a transferência continuava marcando zero, e quem olhava a
    tela concluía que o cadastro não tinha funcionado.

    Então o peso novo alcança o que ainda não saiu, e só isso: movimento
    concluído ou cancelado fica com o número da época, que é história.
    """
    _inherit = 'product.product'

    def write(self, vals):
        res = super().write(vals)
        if 'weight' in vals:
            self._liber_refazer_peso_dos_movimentos()
        return res

    def _liber_refazer_peso_dos_movimentos(self):
        moves = self.env['stock.move'].search([
            ('product_id', 'in', self.ids),
            ('state', 'not in', ('done', 'cancel')),
        ])
        if not moves:
            return
        # Chamar o compute do próprio core e gravar: assim o peso do
        # movimento é recalculado pela mesma regra de sempre, e o peso da
        # transferência — que depende dele — vem atrás sozinho.
        moves._cal_move_weight()
        moves.flush_recordset(['weight'])
