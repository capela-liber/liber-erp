# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class LiberAgedPayable(models.Model):
    """Uma linha aberta de conta a pagar, na faixa de atraso a que pertence
    HOJE.

    Espelho do `liber.aged.receivable`, com o sinal invertido: a pagar vive a
    crédito no razão e o contador quer ler a dívida positiva. A inversão
    acontece no SELECT -- o razão não é tocado.
    """

    _name = 'liber.aged.payable'
    _inherit = 'liber.aged.balance.abstract'
    _description = 'Aged Payable'
    _auto = False

    _aged_account_type = 'liability_payable'
    _aged_sign = -1
    _aged_doc_types = ('in_invoice', 'in_refund', 'in_receipt')

    partner_id = fields.Many2one('res.partner', string='Vendor', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            self._aged_sql(self._table, self._aged_account_type,
                           self._aged_sign, self._aged_doc_types))
