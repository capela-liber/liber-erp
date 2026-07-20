# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    """The consignment universe, as one flag.

    The business rule, in the words of the publisher: "Metabooks é a regra". A
    title can be consigned only if the catalogue says it is a physical book and
    that it is available -- everything else (ebook, audiobook, out of print,
    withdrawn, replaced) is outside the universe, and no amount of curation may
    put it on a shelf.

    Curation happens INSIDE the universe: the template picks from what this flag
    allows. That is why the rule lives here, on the product, and not as a domain
    copy-pasted into every view that needs it -- the coverage report reads the
    same flag, so the universe cannot drift between the two.
    """
    _inherit = 'product.template'

    soc_consignable = fields.Boolean(
        string='Consignable', compute='_compute_soc_consignable', store=True,
        help="In the consignment universe: a physical book (pbook) that "
             "Metabooks lists as available. Titles outside it cannot be put on "
             "a template, and do not count in the coverage report.")

    # '20' is Metabooks' code for "Disponível". Matching the code and not the
    # label keeps this working if the description is ever retranslated.
    _METABOOKS_AVAILABLE = '20'
    _METABOOKS_PHYSICAL = 'pbook'

    @api.depends('metabooks_product_type.name',
                 'metabooks_product_availability.identify_number')
    def _compute_soc_consignable(self):
        for tmpl in self:
            tmpl.soc_consignable = bool(
                tmpl.metabooks_product_type.name == self._METABOOKS_PHYSICAL
                and tmpl.metabooks_product_availability.identify_number
                == self._METABOOKS_AVAILABLE)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    soc_consignable = fields.Boolean(
        related='product_tmpl_id.soc_consignable', store=True,
        string='Consignable')
