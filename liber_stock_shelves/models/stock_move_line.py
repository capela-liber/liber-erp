# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class StockMoveLine(models.Model):
    """As duas guardas da transferência interna (08/10/2026).

    1. A ARMADILHA DA RAIZ. A transferência interna nasce com a raiz do
    armazém (`EL-VG/Stock`) nos dois campos. Deixada na origem, a reserva do
    core desce a árvore (`child_of`), separa da prateleira que recebeu
    primeiro -- muitas vezes a própria prateleira de destino -- e grava a
    linha dela para ela mesma. A transferência valida, o histórico registra,
    e nada muda de lugar: foi o picking 9204 do dev, 25 exemplares "movidos"
    de EL-000043 para EL-000043 com o saldo intocado. O core do 19 não
    compara os dois locais em lugar nenhum. Aqui se recusa a validação quando
    uma linha de tipo interno sai e chega no mesmo local; a mensagem nomeia a
    prateleira e ensina os dois caminhos. Só o tipo interno: o Realocar cria
    movimentos sem tipo de operação, e entrega/recebimento nunca têm origem
    igual ao destino.

    2. DENTRO DO ARMAZÉM. O "Para" da janela Detalhes aceita qualquer local,
    inclusive a prateleira de consignação de um cliente; a constraint do
    cabeçalho (stock_picking.py) não o alcança. Aqui a linha da transferência
    do armazém é conferida na validação.
    """
    _inherit = 'stock.move.line'

    def _action_done(self):
        paradas = self.filtered(
            lambda ml: ml.picking_code == 'internal'
            and ml.quantity
            and ml.location_id == ml.location_dest_id)
        if paradas:
            ml = paradas[0]
            raise UserError(_(
                "Nothing would move: %(qty)s x %(product)s is picked from "
                "%(location)s and stored back to %(location)s.\n\n"
                "Set the shelf the books leave from as the Source Location, "
                "or open Details on the line and pick the stock of the "
                "warehouse root in \"Pick From\".",
                qty=ml.quantity,
                product=ml.product_id.display_name,
                location=ml.location_id.display_name))
        for ml in self.filtered(
                lambda ml: ml.quantity and ml.picking_id.is_shelf_transfer):
            ml.picking_id._raise_if_outside_warehouse(ml.location_id)
            ml.picking_id._raise_if_outside_warehouse(ml.location_dest_id)
        return super()._action_done()
