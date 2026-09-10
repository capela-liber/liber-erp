# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class LiberAgedReceivable(models.Model):
    """Uma linha aberta de conta a receber, com o saldo posto na faixa de
    atraso a que pertence HOJE.

    É view SQL, e não campo calculado, por um motivo prático: faixa de atraso
    depende da data de hoje, então campo armazenado azeda à meia-noite e campo
    não-armazenado não soma em agrupamento -- e a lista agrupada por cliente,
    que é o formato inteiro deste relatório, deixaria de funcionar. A view
    resolve os dois: o Postgres calcula contra `CURRENT_DATE` a cada consulta,
    e o resultado agrega como qualquer coluna de verdade.

    O motor mora em `liber.aged.balance.abstract`, compartilhado com o Aged
    Payable.
    """

    _name = 'liber.aged.receivable'
    _inherit = 'liber.aged.balance.abstract'
    _description = 'Aged Receivable'
    _auto = False

    _aged_account_type = 'asset_receivable'
    _aged_sign = 1
    _aged_doc_types = ('out_invoice', 'out_refund', 'out_receipt')

    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            self._aged_sql(self._table, self._aged_account_type,
                           self._aged_sign, self._aged_doc_types))
