# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    """A transferência conhece a sua nota.

    O vínculo é carimbado pelo ``account.move`` quando a SEFAZ autoriza a NFe
    (ver ``account_move.py`` deste módulo); aqui moram só os campos que a
    logística lê na ficha e os que sustentam os filtros da lista.
    """
    _inherit = 'stock.picking'

    nfe_move_id = fields.Many2one(
        'account.move', string='Fiscal Note', readonly=True, copy=False,
        index='btree_not_null',
        help="The NFe issued for the order behind this transfer. Stamped "
             "automatically when SEFAZ authorizes the note.")
    nfe_numero = fields.Char(
        related='nfe_move_id.focus_numero', string='NFe Number')
    nfe_status = fields.Selection(
        related='nfe_move_id.focus_status', string='NFe Status')
    # Armazenado de propósito: filtro e agrupamento só funcionam em campo que
    # está no banco, e a lista de transferências é a tela da logística.
    has_nfe = fields.Boolean(
        compute='_compute_has_nfe', store=True, string='Has Fiscal Note')
    # O aviso de cancelamento sai uma vez só; sem esta marca, cada consulta do
    # cron a uma nota cancelada repetiria a mensagem no chatter.
    nfe_cancel_notified = fields.Boolean(copy=False)

    @api.depends('nfe_move_id')
    def _compute_has_nfe(self):
        for picking in self:
            picking.has_nfe = bool(picking.nfe_move_id)

    def _liber_carimbar_nota_de_xml(self):
        """Segunda chance do carimbo: resolve a nota desta transferência pelo
        caminho do XML (pedido -> fatura -> painel), para os movs que já
        existiam antes do gancho do painel (ver nfe_xml_panel.py).

        sudo de propósito e só na leitura da fatura: a Logística não tem
        grupo contábil (liber_roles), e a porteira é o picking -- quem pode
        abrir a transferência pode saber qual nota a acompanha.
        """
        self.ensure_one()
        if self.nfe_move_id or not self.sale_id:
            return
        self.sale_id.sudo().invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted'
        )._liber_carimbar_pickings_do_xml()

    def _liber_baixa_de_prateleira(self):
        """Esta transferência é a baixa de um acerto de consignação?

        A baixa sai da prateleira do cliente, não do armazém: os livros já
        estão com ele há meses, e o que se move é propriedade, não carga.
        Não há caixa a contar, peso a pesar nem frete a declarar -- uma nota
        que herdasse transportadora daqui declararia um transporte que nunca
        houve.

        O campo da prateleira é do módulo de consignação, de que este módulo
        não depende; sem ele instalado não existe prateleira, e nenhuma
        transferência é baixa.
        """
        self.ensure_one()
        if 'is_consignment_shelf' not in self.env['stock.location']._fields:
            return False
        return bool(self.location_id.is_consignment_shelf)
