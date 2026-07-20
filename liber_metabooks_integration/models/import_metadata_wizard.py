# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from datetime import datetime
import binascii
import tempfile
from tempfile import TemporaryFile
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)
import io

try:
    import xlrd
except ImportError:
    _logger.debug('Cannot `import xlrd`.')
try:
    import csv
except ImportError:
    _logger.debug('Cannot `import csv`.')
try:
    import base64
except ImportError:
    _logger.debug('Cannot `import base64`.')


class ImportMetadataWizard(models.TransientModel):
    _name = 'import.metadata.wizard'
    _description = 'import metadata wizard'

    metadata_file = fields.Binary(string="Select File")
    vendor_id = fields.Many2one('res.partner', string='Vendor')

    def action_import_metadata(self):
        return

    def action_import_metadata(self):
        """Import Mercado Editorial Sheet from Vendor"""
        flag = self.env['res.users'].has_group('liber_metabooks_integration.metadata_group')
        if not flag:
            raise UserError(u'Permission denied\n You are not allowed to access this Functionality')
        fp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        fp.write(binascii.a2b_base64(self.metadata_file))
        fp.seek(0)
        values = {}
        workbook = xlrd.open_workbook(fp.name)
        sheet = workbook.sheet_by_index(0)
        try:
            message = []
            for row_no in range(sheet.nrows):
                product_type = False
                metabooks_product_availability = False
                bisac_code = False
                bisac_code_ids = [(6, 0, [])]
                author_name_ids = [(6, 0, [])]
                fiscal_classification_id = False

                if row_no <= 0:
                    fields = map(lambda row: row.value.encode('utf-8'), sheet.row(row_no))
                else:
                    line = list(
                        map(lambda row: isinstance(row.value, bytes) and row.value.encode('utf-8') or str(row.value),
                            sheet.row(row_no)))

                    if line[1]:
                        book_type = line[1]
                        if line[1] == 'Livro Impresso':
                            book_type = 'pbook'
                        product_type = self.env['metabooks.book.type'].search([('name', '=', book_type)])
                    # TODO v19 port: NCM ('account.ncm' absent in v19 community)
                    # if line[28]:
                    #     fiscal_classification_id = self.env['account.ncm'].search(
                    #         [('code', '=', line[28])], limit=1).id
                    if line[43]:
                        metabooks_product_availability = self.env['metabooks.avalaibility.definition'].search([]).filtered(lambda x: x.product_definition == line[43])
                    if line[37]:
                        flag = 1
                        bisac_codes = line[37].replace(' ', '')
                        for bisac in bisac_codes.split(','):
                            code = self.env['biblio.bisac.codes'].search([('bisac_code', '=', bisac)], limit=1)
                            if not code:
                                code = self.env['biblio.bisac.codes'].create({'bisac_code': bisac})
                            if code:
                                if flag:
                                    bisac_code = code.id
                                    flag = 0
                                bisac_code_ids[0][2].append(code.id)

                    values = {
                        'isbn': line[0],
                        'metabooks_product_type': product_type.id if product_type else False,
                        'name': line[2],
                        'metabooks_book_title': line[2],
                        'metabooks_book_subtitle': line[3],
                        'edition': line[6],
                        'metabooks_page_count': int(float(line[11] or 0)),
                        'metabooks_weight': float(line[12] or 0),
                        'metabooks_width': float(line[13] or 0),
                        'metabooks_height': float(line[14] or 0),
                        'metabooks_thickness': float(line[15] or 0.0),
                        'list_price': float(line[19] or 0.0),
                        'metabooks_keywords': line[21],
                        'metabooks_image_url': line[22],
                        'size_chart_link': line[23],
                        'barcode': line[27],
                        # 'fiscal_classification_id': fiscal_classification_id,  # TODO v19 port: NCM
                        'synopsys': line[34],
                        'bisac_code': bisac_code,
                        'bisac_code_ids': bisac_code_ids,
                        'default_code': line[41],
                        'metabooks_product_availability': metabooks_product_availability.id if metabooks_product_availability else False,
                        'metabooks_publisher': line[45],
                        'metabooks_label': line[47],
                    }
                    if line[35]:
                        publish_date = ''
                        try:
                            publish_date = xlrd.xldate.xldate_as_datetime(float(line[35]), 1).date()
                        except ValueError as verr:
                            _logger.info('----Type conversion exception in publish date %s ------', verr)
                            publish_date = datetime.strptime(line[48], '%Y-%m-%d').date()
                        if publish_date:
                            values['metabooks_publish_date'] = publish_date
                    if line[48]:
                        update_date = ''
                        try:
                            update_date = xlrd.xldate.xldate_as_datetime(float(line[48]), 1)
                            values['metabooks_last_updatedate'] = update_date
                        except ValueError as verr:
                            _logger.info('----Type conversion exception in upadte date %s ------', verr)
                            update_date = datetime.strptime(line[48], '%Y-%m-%d %H:%M:%S')
                        if update_date:
                            values['metabooks_last_updatedate'] = update_date

                    if values.get('barcode'):
                        product = self.env['product.template'].search([('barcode', '=', values.get('barcode'))])
                        if product:
                            product.update(values)
                        else:
                            product.create(values)
                        message.append(values.get('barcode'))
        except Exception as e:
            _logger.info("========Import Mercado Exception=======%s", e)
            raise ValidationError(_('Error while Importing Data \n %s') % e)
        if message:
            message = 'Vendor Mercado Books Updated - ' + str(message)
            self.vendor_id.message_post(body=message)
        return

