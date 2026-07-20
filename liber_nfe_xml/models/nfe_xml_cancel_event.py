# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class NfeXmlCancelEvent(models.Model):
    """Cancellation events (procEventoNFe, tpEvento 110111/110112).

    These XMLs cancel a previously issued NFe. They carry no emit/dest/items,
    so they do not belong in ``nfe.xml.panel``; they are kept here in their own
    table and linked to the cancelled NFe through the access key (``chNFe``).
    """
    _name = 'nfe.xml.cancel.event'
    _description = "NFe Cancellation Event"
    _order = 'event_date desc, id desc'
    _rec_name = 'key'

    key = fields.Char(string="NFe Key", index='btree_not_null', required=True,
                      copy=False, help="44-digit access key (chNFe) of the "
                                       "cancelled NFe.")
    nfe_id = fields.Many2one('nfe.xml.panel', string="Cancelled NFe",
                             ondelete='set null',
                             help="NFe panel record whose access key matches "
                                  "this cancellation event.")
    tp_evento = fields.Char(string="Event Type", help="110111 Cancelamento / "
                                                       "110112 Cancelamento por Substituicao.")
    protocol = fields.Char(string="Protocol")
    reason = fields.Char(string="Reason")
    event_date = fields.Datetime(string="Event Date")
    desc_evento = fields.Char(string="Description")
    file = fields.Binary(string="Cancellation XML", attachment=True)
    file_name = fields.Char(string="File Name")
    company_id = fields.Many2one('res.company', string="Company")

    _key_uniq = models.Constraint(
        'unique ("key")',
        'A cancellation event for this NFe key already exists!')
