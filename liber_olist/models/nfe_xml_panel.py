# -*- coding: utf-8 -*-

from odoo import fields, models


class NfeXmlPanel(models.Model):
    """Olist provenance on the fiscal document.

    The panel stays source-agnostic (see nfe_xml): the Olist link is added from
    the outside, so removing this module removes the integration without
    touching the ledger.
    """
    _inherit = 'nfe.xml.panel'

    source = fields.Selection(selection_add=[('olist', 'Olist API')],
                              ondelete={'olist': 'set default'})
    olist_account_id = fields.Many2one('olist.account', string="Conta Olist",
                                       readonly=True, copy=False, index=True)
    olist_nota_id = fields.Char(string="ID da nota no Olist", readonly=True,
                                copy=False, index='btree_not_null',
                                help="Id interno da nota no Olist — a alça para "
                                     "buscá-la de novo pela API.")
