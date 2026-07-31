# -*- coding: utf-8 -*-
"""19.0.1 -> 19.0.2: one freight conversation, and it is Odoo's.

The print-quote wizard and the 'Print Delivery' selection are gone (the
dropship route already says where the books go), the shipping method is
called Dropship, and 'Add shipping' lists every transporter Metabrasil
quoted.

The carrier and its freight product live in a noupdate block -- deliberately,
so nobody's margin or excluded-carrier list is reset by an upgrade. That is
exactly why the rename has to happen here: an upgrade will not touch those
records, and `TranslationImporter.save()` skips noupdate records too, so the
.po alone would leave the old name standing in every language but English.
Hence the per-language map: the .po is the source of truth for a FRESH
install, this is the repair crew for the ones already out there.
"""
import logging

_logger = logging.getLogger(__name__)

# xmlid -> {lang: (old name, new name)}. Only what still carries the old name
# is touched: a house that renamed it on purpose keeps its own word.
RENAMES = {
    'liber_metabrasil.delivery_carrier_metabrasil': {
        'en_US': ("Metabrasil", "Dropship"),
        'pt_BR': ("Metabrasil", "Dropship"),
    },
    'liber_metabrasil.product_product_delivery_metabrasil': {
        'en_US': ("Metabrasil Freight", "Dropship Freight"),
        'pt_BR': ("Frete MetaBrasil", "Frete Dropship"),
    },
}


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    installed = set(dict(env['res.lang'].get_installed()))
    for xmlid, per_lang in RENAMES.items():
        record = env.ref(xmlid, raise_if_not_found=False)
        if not record:
            continue
        for lang, (old_name, new_name) in per_lang.items():
            if lang != 'en_US' and lang not in installed:
                continue
            translated = record.with_context(lang=lang)
            if translated.name == old_name:
                translated.name = new_name
                _logger.info("liber_metabrasil: %s [%s] renamed to %r",
                             xmlid, lang, new_name)
