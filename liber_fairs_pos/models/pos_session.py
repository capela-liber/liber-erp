# -*- coding: utf-8 -*-
"""O balcão carrega a mesa junto com os produtos.

A quantidade que interessa a quem vende na feira é a da MESA, e ela só existe
se alguém disser de qual mesa se fala. É aqui: o carregamento do caixa entra
com a localização da feira no contexto, e o campo `fair_qty` do produto sabe
o que responder.

A ASSINATURA É A DO NÚCLEO, e nada além dela. Inventar um parâmetro aqui
(`only_data`, que não existe em `load_data`) derruba o Ponto de Venda inteiro
na hora de abrir, com uma mensagem que não diz nada a quem está na feira.
"""
from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def load_data(self, models_to_load):
        feira = self.config_id.fair_id
        registro = self
        if feira and feira.stock_location_id:
            registro = self.with_context(
                fair_location_id=feira.stock_location_id.id)
        return super(PosSession, registro).load_data(models_to_load)

    def get_fair_shelf_qty(self):
        """Quantos exemplares há NA MESA, AGORA.

        O número não pode viajar só no carregamento do produto. O balcão do
        19 guarda os produtos no navegador (IndexedDB) e só volta a buscá-los
        quando o `write_date` do produto muda -- e mover caixa de livro não
        escreve nada no produto. O resultado é uma etiqueta congelada: quem
        abriu o caixa antes de a mercadoria chegar via zero para sempre,
        mesmo fechando e reabrindo.

        Por isso a mesa se lê ao vivo, por esta chamada, e o balcão a repete
        de tempos em tempos e depois de cada venda sincronizada.
        """
        self.ensure_one()
        feira = self.config_id.fair_id
        local = feira.stock_location_id if feira else False
        if not local:
            return {}
        agrupado = self.env['stock.quant'].sudo()._read_group(
            [('location_id', 'child_of', local.id)],
            ['product_id'], ['quantity:sum'])
        na_mesa = {}
        for produto, quantidade in agrupado:
            modelo = produto.product_tmpl_id.id
            na_mesa[modelo] = na_mesa.get(modelo, 0.0) + quantidade
        return na_mesa
