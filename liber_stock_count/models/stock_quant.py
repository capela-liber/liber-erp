# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import AccessError


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _liber_check_can_apply_inventory(self):
        """Quem aplica o ajuste é o administrador do Inventário.

        Contar é preencher "Contado"; aplicar é transformar a diferença num
        movimento que muda a quantidade em mãos. O core dá os dois gestos ao
        mesmo grupo (Inventário > Usuário); aqui o segundo é só do
        ``stock.group_stock_manager``. Superusuário passa: código com
        ``sudo()`` é fronteira aceita, como nas outras travas da casa.

        Levanta AccessError, não UserError: é direito, não dado errado.
        """
        if self.env.su or self.env.user.has_group('stock.group_stock_manager'):
            return
        raise AccessError(_(
            "Only an Inventory administrator can apply an inventory "
            "adjustment and change the quantity on hand. Your count is kept "
            "in the Counted column: ask the warehouse manager to review and "
            "apply it."))

    def _apply_inventory(self, date=None):
        # Todo ajuste passa por aqui: o Aplicar da linha, o Aplicar tudo com
        # motivo, a caixa de conflito, a ficha do produto, o apagar do quant.
        self._liber_check_can_apply_inventory()
        return super()._apply_inventory(date=date)

    def action_apply_inventory(self, date=None):
        # Quando a quantidade mudou desde a contagem, o core abre a caixa de
        # conflito ANTES de aplicar. A recusa vem antes dela, para quem conta
        # receber a mesma resposta nos dois casos.
        self._liber_check_can_apply_inventory()
        return super().action_apply_inventory(date=date)

    def action_apply_all(self):
        self._liber_check_can_apply_inventory()
        return super().action_apply_all()
