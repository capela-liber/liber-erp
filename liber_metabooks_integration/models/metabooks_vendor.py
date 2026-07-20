from odoo import models, fields, api, _
from datetime import date, datetime
from odoo.exceptions import ValidationError
import logging
from io import BytesIO
import base64
import xlsxwriter
import tempfile
import binascii
import xlrd
from xlsxwriter.utility import xl_rowcol_to_cell
import urllib
import requests
import json

_logger = logging.getLogger(__name__)


class IsbnBookPrefixes(models.Model):
    _name = 'metabooks.isbn.code.prefix'
    _description = 'ISBN PREFIXES'

    name = fields.Char('Isbn Prefix')


class MetabooksPartner(models.Model):
    _inherit = 'res.partner'

    metabooks_editor_id = fields.Char('Metabooks Edito Id')
    metabooks_automatic_sync_products = fields.Boolean('Sync Product Automatically')
    isbn_prefixes = fields.Many2many('metabooks.isbn.code.prefix', string='Isbn Prefxes')
    metaoook_update_book_also = fields.Boolean('Update Book Also')
    metabooks_update_by_lastdate = fields.Boolean('Update By LastUpdateDate', default=True)
    vendor_metabooks_ids = fields.One2many('vendor.metabooks.ids', 'partner_id', string='Metabooks ids')
    pricelist_lead_time = fields.Integer('Lead Time')

    def sync_vendor_metabooks(self):
        if self.metabooks_editor_id:
            pass
        else:
            raise ValidationError('Enter Publisher id')

    def import_metadata(self):
        self.ensure_one()
        for rec in self:
            return {
                'name': _('Add Xml File'),
                'type': 'ir.actions.act_window',
                'res_model': 'import.metadata.wizard',
                'view_id': self.env.ref('liber_metabooks_integration.import_metadata_wizard_view_form').id,
                'view_type': 'form',
                'view_mode': 'form',
                'context': {'default_vendor_id': rec.id},
                'target': 'new',
            }


class VendorMetabooksId(models.Model):
    _name = 'vendor.metabooks.ids'
    _description = "Metabooks Vendors"
    _rec_name = 'metabooks_editor_id'

    # partner_id = fields.Many2one('res.partner', domain=[('supplier_rank', '>', 0)])
    partner_id = fields.Many2one('res.partner')
    metabooks_editor_id = fields.Char('Metabooks Id', required=True)
    brand = fields.Char('Brand')
    company_id = fields.Many2one('res.company', string="Company Id")

    _sql_constraints = [
        ('metabooks_editor_id_ref_uniq', 'unique (metabooks_editor_id)', 'Metabooks Id must be unique !'),
    ]

    def action_import_catalog(self):
        """Queue a background job to import this publisher's whole catalogue.

        The import runs page by page in a cron (resumable), so a large catalogue
        never blocks the web request past the worker time limit.
        """
        self.ensure_one()
        if not self.metabooks_editor_id:
            raise ValidationError(_("Set the Metabooks Id (mvbId / VL) first."))
        job = self.env['metabooks.import.job'].create_and_run(self.metabooks_editor_id)
        return job.open_form_action()

    def export_metadata(self):
        """To export Metabooks Data for a Vendor in Xls Sheet:"""

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet()
        # set column format
        worksheet.set_default_row(18)
        worksheet.set_column(0, 60, 10)
        # add headers in xlsx
        headers_bold = workbook.add_format({
            'bold': True,
            'size': 10,
        })

        worksheet.write('A1', 'ISBN', headers_bold)
        worksheet.write('B1', 'Formato', headers_bold)
        worksheet.write('C1', 'Título', headers_bold)
        worksheet.write('D1', 'Subtítulo', headers_bold)
        worksheet.write('E1', 'Título Original', headers_bold)
        worksheet.write('F1', 'Volume do título', headers_bold)
        worksheet.write('G1', 'Edição', headers_bold)
        worksheet.write('H1', 'Ano', headers_bold)
        worksheet.write('I1', 'Detalhes da edição', headers_bold)
        worksheet.write('J1', 'Coleção', headers_bold)
        worksheet.write('K1', 'Volume da coleção', headers_bold)
        worksheet.write('L1', 'Páginas', headers_bold)
        worksheet.write('M1', 'Peso', headers_bold)
        worksheet.write('N1', 'Largura', headers_bold)
        worksheet.write('O1', 'Altura', headers_bold)
        worksheet.write('P1', 'Espessura', headers_bold)
        worksheet.write('Q1', 'Plataformas disponíveis (e-book)', headers_bold)
        worksheet.write('R1', 'DRM (e-book)', headers_bold)
        worksheet.write('S1', 'Formato de arquivo (e-book)', headers_bold)
        worksheet.write('T1', 'Preço', headers_bold)
        worksheet.write('U1', 'Moeda', headers_bold)
        worksheet.write('V1', 'Palavras-chave', headers_bold)
        worksheet.write('W1', 'Link para o livro', headers_bold)
        worksheet.write('X1', 'Link para o booktrailer', headers_bold)
        worksheet.write('Y1', 'Encadernação', headers_bold)
        worksheet.write('Z1', 'Área', headers_bold)
        worksheet.write('AA1', 'Origem', headers_bold)
        worksheet.write('AB1', 'Código de Barras', headers_bold)
        worksheet.write('AC1', 'Classificação Fiscal', headers_bold)
        worksheet.write('AD1', 'Faixa Etária', headers_bold)
        worksheet.write('AE1', 'Ano/Série', headers_bold)
        worksheet.write('AF1', 'Grau', headers_bold)
        worksheet.write('AG1', 'Matéria', headers_bold)
        worksheet.write('AH1', 'Sumário', headers_bold)
        worksheet.write('AI1', 'Sinopse', headers_bold)
        worksheet.write('AJ1', 'Data de Publicação', headers_bold)
        worksheet.write('AK1', 'CDD', headers_bold)
        worksheet.write('AL1', 'BISACs', headers_bold)
        worksheet.write('AM1', 'Idiomas', headers_bold)
        worksheet.write('AN1', 'Material adicional', headers_bold)
        worksheet.write('AO1', 'Classificação indicativa', headers_bold)
        worksheet.write('AP1', 'Código interno', headers_bold)
        worksheet.write('AQ1', 'Certificação inmetro', headers_bold)
        worksheet.write('AR1', 'Status', headers_bold)
        worksheet.write('AS1', 'Data de Previsão de Disponibilidade', headers_bold)
        worksheet.write('AT1', 'Editora', headers_bold)
        worksheet.write('AU1', 'CNPJ', headers_bold)
        worksheet.write('AV1', 'Selo', headers_bold)
        worksheet.write('AW1', 'Data da última atualização', headers_bold)
        worksheet.write('AX1', 'Autoria', headers_bold)
        worksheet.write('AY1', 'Contribuição', headers_bold)
        worksheet.write('AZ1', 'ISBNs relacionados', headers_bold)
        worksheet.write('BA1', 'URL da primeira capa', headers_bold)
        worksheet.write('BB1', 'URL da quarta capa', headers_bold)
        worksheet.write('BC1', 'URL das imagens internas', headers_bold)
        worksheet.write('BD1', 'URL das imagens em perspectiva', headers_bold)

        row = 1
        col = 0

        for rec in self:
            if rec.partner_id and rec.metabooks_editor_id:
                # get metabooks from vendor and search on book panel
                vendor = rec.partner_id
                metabooks_id = rec.metabooks_editor_id

                if metabooks_id:
                    query = """select id, default_code, metabooks_book_title, metabooks_vendor_id 
                            from product_template where metabooks_vendor_id = %s 
                            """
                    self.env.cr.execute(query, (metabooks_id,))
                    query_data = self.env.cr.fetchall()
                    if not query_data:
                        pass
                    # insert books linking with seller book details panel
                    for book in query_data:
                        content = {}
                        # data = self.env['metabooks.api.call'].get_isbn_data(book[1])
                        product = self.env['product.template'].browse(book[0])
                        if product:
                            content['isbn'] = product.barcode or ''
                            content['format'] = product.metabooks_product_type.name or ''
                            content['title'] = product.metabooks_book_title or ' '
                            content['subtitle'] = product.metabooks_book_subtitle or ''
                            content['title_original'] = ''
                            content['volume_title'] = ''
                            content['edition'] = product.edition or ''
                            content['year'] = str(product.metabooks_publish_date.year) if product.metabooks_publish_date else ''
                            content['edition_details'] = ''
                            content['collection'] = ''
                            content['collection_volume'] = ''
                            content['pages'] = product.metabooks_page_count or ''
                            content['weight'] = product.metabooks_weight or ''
                            content['width'] = product.metabooks_width or ''
                            content['height'] = product.metabooks_height or ''
                            content['thickness'] = product.metabooks_thickness or ''
                            content['platform'] = ''
                            content['drm_ebook'] = 'Y' if product.metabooks_product_type.name == 'ebook' else 'N'
                            content['format_ebook'] = ''
                            content['price'] = product.list_price or 0
                            content['coin'] = ''
                            content['keywords'] = product.metabooks_keywords
                            content['book_link'] = product.metabooks_image_url or ''
                            content['booktrailor_link'] = product.size_chart_link or ''
                            content['binding'] = product.binding
                            content['area'] = ''

                            content['origin'] = product.metabooks_publication_country.name \
                                if product.metabooks_publication_country else ''
                            content['barcode'] = product.barcode
                            # NCM / fiscal_classification_id disabled in v19 port (no
                            # account.ncm without l10n_br); leave blank until a v19 NCM model.
                            content['fiscal'] = ''
                            content['age_range'] = ''
                            content['serie'] = ''
                            content['degree'] = ''
                            content['matter'] = ''
                            content['summary'] = ''
                            content['sinopse'] = product.synopsys
                            content['publication_date'] = str(product.metabooks_publish_date)
                            content['cdd'] = ''
                            bisac_codes = ''
                            bisac_code_list = product.bisac_code_ids.mapped('bisac_code')
                            for code in bisac_code_list:
                                if not code == bisac_code_list[-1]:
                                    bisac_codes = bisac_codes + code + ','
                                else:
                                    bisac_codes = bisac_codes + code
                            content['bisac'] = bisac_codes
                            content['languages'] = ''
                            content['additional_material'] = ''
                            content['parental_rating'] = 'Livre para todos os públicos' \
                                if product.metabooks_parental_rating == '00' else 'Não recomendado para menores de 16 anos'
                            content['internal_code'] = product.default_code
                            content['immentro_certification'] = ''
                            content['status'] = product.metabooks_product_availability.product_definition \
                                if product.metabooks_product_availability else ''
                            content['available_forecastdate'] = ''
                            content['publishing_company'] = product.metabooks_publisher
                            content['cnpj'] = vendor.cnpj_cpf if vendor else ''
                            content['seal'] = product.metabooks_label
                            content['last_updatedate'] = str(
                                product.metabooks_last_updatedate) if product.metabooks_last_updatedate else ''
                            authors = []
                            contributors = []
                            for author in product.book_auther_ids:
                                if author.author_contributor_role.name != 'A01':
                                    contributors.append(author.author_full_name)
                                else:
                                    authors.append(author.author_full_name)

                            content['authorship'] = str(','.join(authors))
                            content['contribution'] = str(','.join(contributors))
                            content['related_isbn'] = str(product.product_id_values or '')
                            content['first_cover_url'] = product.metabooks_image_url
                            content['fourth_cover_url'] = ''
                            content['internal_image_url'] = ''
                            content['perspective_image_url'] = ''

                        if content:
                            worksheet.write(row, col, content['isbn'] or '')
                            worksheet.write(row, col + 1, content['format'] or '')
                            worksheet.write(row, col + 2, content['title'] or '')
                            worksheet.write(row, col + 3, content['subtitle'] or '')
                            worksheet.write(row, col + 4, content['title_original'] or '')
                            worksheet.write(row, col + 5, content['volume_title'] or '')
                            worksheet.write(row, col + 6, content['edition'] or '')
                            worksheet.write(row, col + 7, content['year'] or '')
                            worksheet.write(row, col + 8, content['edition_details'] or '')
                            worksheet.write(row, col + 9, content['collection'] or '')
                            worksheet.write(row, col + 10, content['collection_volume'] or '')
                            worksheet.write(row, col + 11, content['pages'] or '')
                            worksheet.write(row, col + 12, content['weight'] or '')
                            worksheet.write(row, col + 13, content['width'] or '')
                            worksheet.write(row, col + 14, content['height'] or '')
                            worksheet.write(row, col + 15, content['thickness'] or '')
                            worksheet.write(row, col + 16, content['platform'] or '')
                            worksheet.write(row, col + 17, content['drm_ebook'] or '')
                            worksheet.write(row, col + 18, content['format_ebook'] or '')
                            worksheet.write(row, col + 19, content['price'] or '')
                            worksheet.write(row, col + 20, content['coin'] or '')
                            worksheet.write(row, col + 21, content['keywords'] or '')
                            worksheet.write_url(row, col + 22, content['book_link'] or '')
                            worksheet.write_url(row, col + 23, content['booktrailor_link'] or '')
                            worksheet.write(row, col + 24, content['binding'] or '')
                            worksheet.write(row, col + 25, content['area'] or '')

                            worksheet.write(row, col + 26, content['origin'] or '')
                            worksheet.write(row, col + 27, content['barcode'] or '')
                            worksheet.write(row, col + 28, content['fiscal'] or '')
                            worksheet.write(row, col + 29, content['age_range'] or '')
                            worksheet.write(row, col + 30, content['year'] or '')
                            worksheet.write(row, col + 31, content['degree'] or '')
                            worksheet.write(row, col + 32, content['matter'] or '')
                            worksheet.write(row, col + 33, content['summary'] or '')
                            worksheet.write(row, col + 34, content['sinopse'] or '')
                            worksheet.write(row, col + 35, content['publication_date'] or '')
                            worksheet.write(row, col + 36, content['cdd'] or '')
                            worksheet.write(row, col + 37, content['bisac'] or '')
                            worksheet.write(row, col + 38, content['languages'] or '')
                            worksheet.write(row, col + 39, content['additional_material'] or '')
                            worksheet.write(row, col + 40, content['parental_rating'] or '')
                            worksheet.write(row, col + 41, content['internal_code'] or '')
                            worksheet.write(row, col + 42, content['immentro_certification'] or '')
                            worksheet.write(row, col + 43, content['status'] or '')
                            worksheet.write(row, col + 44, content['available_forecastdate'] or '')
                            worksheet.write(row, col + 45, content['publishing_company'] or '')
                            worksheet.write(row, col + 46, content['cnpj'] or '')
                            worksheet.write(row, col + 47, content['seal'] or '')
                            worksheet.write(row, col + 48, content['last_updatedate'] or '')
                            worksheet.write(row, col + 49, content['authorship'] or '')
                            worksheet.write(row, col + 50, content['contribution'] or '')
                            worksheet.write(row, col + 51, content['related_isbn'] or '')
                            worksheet.write_url(row, col + 52, content['first_cover_url'] or '')
                            worksheet.write_url(row, col + 53, content['fourth_cover_url'] or '')
                            worksheet.write_url(row, col + 54, content['internal_image_url'] or '')
                            worksheet.write_url(row, col + 55, content['perspective_image_url'] or '')

                            row += 1

        workbook.close()
        xlsx_data = output.getvalue()

        if row == 1:
            _logger.info('====No Products forund for these vendors')
            raise ValidationError(_('No products found'))
        else:
            attach = self.env['ir.attachment'].create({
                'name': u'Mercadoeditorial-' + str(self[0].id if self else '') + '.xlsx',
                'datas': base64.b64encode(xlsx_data),
                'datas_fname': 'Mercadoeditorial-' + str(self[0].id if self else '') + '.xlsx',
                'res_model': 'vendor.metabooks.ids',
                'res_id': self[0].id if self else 0,
                'type': 'binary'
            })

            action = {
                'name': 'Mercadoeditorial',
                'type': 'ir.actions.act_url',
                'url': "web/content/?model=ir.attachment&id=" + str(attach.id) +
                       "&filename_field=datas_fname&field=datas&download=true&filename=" + attach.datas_fname,
                'target': 'self',
            }
            return action
