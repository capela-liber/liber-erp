# -*- coding: utf-8 -*-

from odoo import api, fields, models, _

# tpEvento values we give a name to. Anything else is filed as 'other' - the
# table takes every event now, so an unknown code is stored, not discarded.
EV_CORRECTION = '110110'          # Carta de Correcao Eletronica (CC-e)
EV_CANCEL = '110111'              # Cancelamento
EV_CANCEL_REPLACE = '110112'      # Cancelamento por Substituicao
EV_MANIFEST = ('210200', '210210', '210220', '210240')


class NfeXmlCancelEvent(models.Model):
    """Events of an NFe (procEventoNFe): cancellations and correction letters.

    These XMLs carry no emit/dest/items, so they do not belong in
    ``nfe.xml.panel``; they live here and are linked to the note through the
    access key (``chNFe``).

    LAB FORK history: the table started out holding cancellations only
    (tpEvento 110111/110112) and the import DISCARDED everything else, so
    every correction letter the house ever received was thrown away. It now
    takes any event. The model keeps its ``nfe.xml.cancel.event`` name on
    purpose - renaming it would mean migrating the stored data and every XML
    id that points at it, for no gain.
    """
    _name = 'nfe.xml.cancel.event'
    _description = "NFe Event"
    _order = 'event_date desc, id desc'
    _rec_name = 'key'

    key = fields.Char(string="NFe Key", index='btree_not_null', required=True,
                      copy=False, help="44-digit access key (chNFe) of the "
                                       "NFe this event refers to.")
    nfe_id = fields.Many2one('nfe.xml.panel', string="NFe",
                             ondelete='set null',
                             help="NFe panel record whose access key matches "
                                  "this event.")
    tp_evento = fields.Char(string="Event Type", help="110110 Carta de Correcao / "
                                                      "110111 Cancelamento / "
                                                      "110112 Cancelamento por Substituicao.")
    # A note can carry several correction letters, numbered from 1. This is
    # what makes the uniqueness key (chNFe, tpEvento, nSeqEvento) instead of
    # the chNFe alone - the old constraint would keep only the first CC-e.
    n_seq_evento = fields.Integer(string="Sequence", default=1,
                                  help="nSeqEvento: 1 for a cancellation, "
                                       "1..20 for successive correction letters.")
    event_kind = fields.Selection(
        [('cancel', 'Cancellation'), ('correction', 'Correction Letter'),
         ('manifest', 'Manifestation'), ('other', 'Other')],
        string="Kind", compute='_compute_event_kind', store=True,
        help="Derived from the event type, so the list can be filtered and "
             "the accountant's export can file each XML in its own folder.")
    protocol = fields.Char(string="Protocol")
    reason = fields.Char(string="Reason", help="xJust: why the NFe was cancelled.")
    correction_text = fields.Text(string="Correction",
                                  help="xCorrecao: what the correction letter "
                                       "states. Empty on a cancellation.")
    event_date = fields.Datetime(string="Event Date")
    desc_evento = fields.Char(string="Description")
    file = fields.Binary(string="Event XML", attachment=True)
    file_name = fields.Char(string="File Name")
    company_id = fields.Many2one('res.company', string="Company")

    _event_uniq = models.Constraint(
        'unique ("key", tp_evento, n_seq_evento)',
        'This NFe event is already registered!')

    @api.depends('tp_evento')
    def _compute_event_kind(self):
        for event in self:
            code = (event.tp_evento or '').strip()
            if code in (EV_CANCEL, EV_CANCEL_REPLACE):
                event.event_kind = 'cancel'
            elif code == EV_CORRECTION:
                event.event_kind = 'correction'
            elif code in EV_MANIFEST:
                event.event_kind = 'manifest'
            else:
                event.event_kind = 'other'

    @api.depends('key', 'event_kind', 'n_seq_evento')
    def _compute_display_name(self):
        labels = dict(self._fields['event_kind'].selection)
        for event in self:
            kind = labels.get(event.event_kind, _('Event'))
            if event.event_kind == 'correction':
                kind = '%s %s' % (kind, event.n_seq_evento or 1)
            event.display_name = '%s - %s' % (event.key or '?', kind)
