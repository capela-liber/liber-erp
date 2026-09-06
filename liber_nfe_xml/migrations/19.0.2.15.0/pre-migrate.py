# -*- coding: utf-8 -*-
"""Make room for more than one event per NFe.

The events table was born holding cancellations only, with ``unique(key)`` —
one row per access key. A note can carry up to twenty correction letters, so
that constraint would keep the first CC-e and reject every other one. It is
replaced by ``unique(key, tp_evento, n_seq_evento)``.

Dropping the old constraint here, before the ORM builds the new one, keeps the
upgrade from failing on a table that momentarily has to satisfy both.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # The column is created by the ORM later in the upgrade; creating it now
    # lets the constraint below be built in the same pass, and gives the rows
    # already in the table the sequence a cancellation always has.
    cr.execute("""
        ALTER TABLE nfe_xml_cancel_event
        ADD COLUMN IF NOT EXISTS n_seq_evento integer
    """)
    cr.execute("UPDATE nfe_xml_cancel_event SET n_seq_evento = 1 "
               "WHERE n_seq_evento IS NULL")

    cr.execute("""
        ALTER TABLE nfe_xml_cancel_event
        DROP CONSTRAINT IF EXISTS nfe_xml_cancel_event_key_uniq
    """)
    # ir_model_constraint remembers what the module declared; leaving the stale
    # row behind makes a later upgrade try to restore the constraint we just
    # dropped.
    cr.execute("""
        DELETE FROM ir_model_constraint
        WHERE name = 'nfe_xml_cancel_event_key_uniq'
    """)
    _logger.info("liber_nfe_xml: unique(key) dropped from nfe_xml_cancel_event "
                 "- correction letters can now coexist with the cancellation.")
