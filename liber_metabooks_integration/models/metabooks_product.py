# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..services import onix_codes

_logger = logging.getLogger(__name__)


class MetabooksProduct(models.Model):
    _inherit = 'product.template'

    synopsys = fields.Char("Synopsys", tracking=True)
    size_chart = fields.Binary(help="", string='Size Chart', attachment=True)
    size_chart_name = fields.Char()
    metabooks_image_url = fields.Text('Metabooks Image', tracking=True)
    metabooks_vendor_id = fields.Char('Vendor Metabooks Id', tracking=True)
    metabooks_weight = fields.Float('Metabooks Weight', tracking=True)
    metabooks_height = fields.Float('Height', tracking=True)
    metabooks_width = fields.Float('Width', tracking=True)
    metabooks_creation_date = fields.Date('Creation Date', tracking=True)
    metabooks_page_count = fields.Integer("Page Count", tracking=True)
    metabooks_subjects = fields.Many2many('metabooks.book.subjects', string='Metabooks Subjects', copy=False, tracking=True)
    metabooks_json_data = fields.Binary('Json file', tracking=True)
    product_identifier = fields.Many2many('metabooks.product.identifier', tracking=True)
    metabooks_publish_date = fields.Date('Metabooks Publish Date', tracking=True)
    metabooks_book_title = fields.Char('Book Title', tracking=True)
    metabooks_product_type = fields.Many2one('metabooks.book.type', string='Book Type', tracking=True)
    metabooks_product_availability = fields.Many2one('metabooks.avalaibility.definition', string='Product Availability', tracking=True)
    metabooks_product_status = fields.Boolean('Status', default=True, tracking=True)
    metabooks_publisher = fields.Char('Publisher', tracking=True)
    metabooks_label = fields.Char('label', tracking=True)
    bisac_code = fields.Many2one('biblio.bisac.codes', string='BISAC', tracking=True)
    bisac_prefix = fields.Char('Bisac prefix', tracking=True)
    bisac_code_ids = fields.Many2many('biblio.bisac.codes', string='BISAC List', tracking=True)
    metabooks_keywords = fields.Text('Metabooks Keywords', tracking=True)

    metabooks_thickness = fields.Float('Metabooks Thickness', tracking=True)
    metabooks_book_subtitle = fields.Char('Book Subitle', tracking=True)
    metabooks_last_updatedate = fields.Datetime('Last Modified Date', tracking=True)
    metabooks_parental_rating = fields.Char('Parental Rating', tracking=True)
    metabooks_collections = fields.Char('Metabooks Collections', tracking=True)
    metabooks_publication_country = fields.Many2one('res.country', string='Metabooks Publication Country', tracking=True)
    size_chart_link = fields.Text('Size Chart Link')
    product_relation_codes = fields.Text('Related Product Codes')
    product_id_values = fields.Text('Related Products')

    book_auther_ids = fields.Many2many('metabooks.auther.publiser', string='Author List', tracking=True)
    isbn_publisher_id = fields.Many2one('metabooks.auther.publiser', string='ISBN Publisher')
    publish_date = fields.Char("Publish Date(S)")
    binding = fields.Char("Binding", tracking=True)
    isbn = fields.Char("ISBN")
    edition = fields.Char("Edition", tracking=True)
    excerpt = fields.Char("Excerpt")
    prices = fields.Char("Prices", tracking=True)
    isbn_subject = fields.Many2many('isbn.book.subjects', string='ISBN Subjects')

    # ------------------------------------------------------------------ #
    #  Technical sheet (ONIX). The physical specification of the book: this
    #  is what a print/graphic-services order is quoted from, so every field
    #  here is a fact a printer asks for. Only the by-ISBN ONIX call carries
    #  it -- the catalogue feed does not -- hence action_metabooks_refresh_technical.
    # ------------------------------------------------------------------ #
    metabooks_product_form = fields.Selection(
        onix_codes.PRODUCT_FORM, string='Product Form', tracking=True,
        help="ONIX product form (list 150): paperback, hardback, digital...")
    metabooks_binding = fields.Selection(
        onix_codes.BINDING, string='Binding', tracking=True,
        help="How the block is bound (ONIX product form detail, B3xx). Sewn "
             "signatures and a glued spine are different jobs on a print order.")
    metabooks_form_detail = fields.Char(
        'Form Detail Codes', tracking=True,
        help="Raw ONIX product form detail codes, kept for audit.")
    metabooks_has_flaps = fields.Boolean('With Flaps', tracking=True)
    metabooks_has_dust_jacket = fields.Boolean('With Dust Jacket', tracking=True)
    metabooks_has_thumb_index = fields.Boolean('With Thumb Index', tracking=True)
    metabooks_has_ribbon = fields.Boolean('With Ribbon Marker', tracking=True)
    metabooks_ebook_format = fields.Char('E-book Format', tracking=True)
    metabooks_front_matter_pages = fields.Integer('Front Matter Pages', tracking=True)
    metabooks_back_matter_pages = fields.Integer('Back Matter Pages', tracking=True)
    metabooks_total_page_count = fields.Integer(
        'Total Pages', compute='_compute_metabooks_total_page_count', store=True,
        help="Main content plus front and back matter: the sheet count a printer bills.")
    metabooks_illustration_count = fields.Integer('Illustrations', tracking=True)
    metabooks_illustration_note = fields.Char('Illustration Note', tracking=True)
    metabooks_ncm = fields.Char(
        'NCM', tracking=True,
        help="Brazilian fiscal classification, as declared to Metabooks "
             "(ONIX product classification type 10).")
    metabooks_language = fields.Char('Language', tracking=True)
    metabooks_original_language = fields.Char(
        'Original Language', tracking=True,
        help="Language the work was translated from, when it is a translation.")
    metabooks_publishing_status = fields.Selection(
        onix_codes.PUBLISHING_STATUS, string='Publishing Status', tracking=True,
        help="Editorial life of the title (ONIX list 64). Not the same as "
             "availability: a title can be Active and still out of stock.")
    metabooks_publication_city = fields.Char('Publication City', tracking=True)
    metabooks_country_of_manufacture = fields.Many2one(
        'res.country', string='Country of Manufacture', tracking=True,
        help="Where the book was physically printed.")
    metabooks_edition_number = fields.Integer('Edition Number', tracking=True)
    metabooks_edition_type = fields.Char('Edition Type', tracking=True)
    metabooks_technical_sync = fields.Datetime(
        'Technical Data Synced', readonly=True,
        help="Last time the technical sheet was pulled from the by-ISBN ONIX record.")

    ks_product_brand_id = fields.Many2one('product.category', string='Brand')

    new_books_published = fields.Boolean('New Book', default=False)
    # TODO v19 port: NCM fiscal classification. The 'account.ncm' model does not
    # exist in Odoo 19 community l10n_br. Disabled until a v19 NCM model is chosen.
    # fiscal_classification_id = fields.Many2one(
    #     'account.ncm', string=u"Classificação Fiscal (NCM)")

    @api.depends('metabooks_page_count', 'metabooks_front_matter_pages',
                 'metabooks_back_matter_pages')
    def _compute_metabooks_total_page_count(self):
        for product in self:
            product.metabooks_total_page_count = (
                (product.metabooks_page_count or 0)
                + (product.metabooks_front_matter_pages or 0)
                + (product.metabooks_back_matter_pages or 0))

    def action_metabooks_refresh_technical(self):
        """Pull the technical sheet from Metabooks for the selected books.

        Only the physical/ONIX specification is written: title, price, category
        and cover are left alone, so refreshing a book never undoes editorial or
        commercial work done in Odoo.
        """
        isbns = [p.default_code or p.barcode for p in self
                 if (p.default_code or p.barcode)]
        if not isbns:
            raise ValidationError(_(
                "None of the selected products has an ISBN to look up on Metabooks."))
        res = self.env['metabooks.connector'].enrich_isbns(isbns)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Metabooks'),
                'message': _('%(updated)s book(s) updated, %(missing)s not found.',
                             updated=res['updated'], missing=len(res['not_found'])),
                'sticky': False,
            },
        }

    def update_metabooks_books(self):
        """Product form button: refresh this book from Metabooks by its ISBN."""
        for product in self:
            isbn = product.default_code or product.barcode
            if not isbn:
                raise ValidationError(_(
                    "This product has no ISBN (Internal Reference or Barcode) "
                    "to look up on Metabooks."))
            self.env['metabooks.connector'].import_isbns([isbn])
        return True

    def set_old_book(self):
        for rec in self:
            rec.new_books_published = False
