# -*- coding: utf-8 -*-
# Copyright (C) EdLab Press
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
import logging
import os

try:
    from BytesIO import BytesIO
except ImportError:
    from io import BytesIO
import zipfile
from odoo.tools import config
from datetime import datetime
from odoo import http
from odoo.http import request, content_disposition
import ast

_logger = logging.getLogger(__name__)


class Binary(http.Controller):
    # LAB FORK / Odoo 19: auth switched from "public" to "user" - these
    # endpoints expose fiscal documents and must not be anonymous.
    @http.route('/web/binary/liber_nfe_xml/download_document', type='http', auth="user")
    def download_document(self, tab_id, **kw):
        new_tab = ast.literal_eval(tab_id)
        attachment_ids = request.env['nfe.xml.panel'].search([('id', 'in', new_tab)])
        file_dict = {}
        for attachment_id in attachment_ids:
            file_store = attachment_id.file
            if file_store:
                file_name = attachment_id.file_name
                file_dict["%s:%s" % (file_store, file_name)] = dict(data=file_store, name=file_name)
            # if file_store:
            #     file_name = attachment_id.name
            #     file_path = attachment_id._full_path(file_store)
            #     file_dict["%s:%s" % (file_store, file_name)] = dict(path=file_path, name=file_name)
        zip_filename = datetime.now()
        zip_filename = "%s.zip" % zip_filename
        bitIO = BytesIO()
        zip_file = zipfile.ZipFile(bitIO, "w", zipfile.ZIP_DEFLATED)
        path = config.options.get('data_dir')
        for file_info in file_dict.values():
            file_path = os.path.join(path, file_info['name'])
            with open(file_path, 'wb') as xml_file:
                xml_file.write(base64.b64decode(file_info['data'].decode('utf-8')))
                xml_file.close()

        for file_info in file_dict.values():
            file_path = os.path.join(path, file_info['name'])
            zip_file.write(file_path, file_info['name'])
            os.remove(file_path)
        zip_file.close()

        # for file_info in file_dict.values():
        #     file_path = os.path.join(path, file_info['name'])
        #     os.remove(file_path)
        return request.make_response(bitIO.getvalue(),
                                     headers=[('Content-Type', 'application/x-zip-compressed'),
                                              ('Content-Disposition', content_disposition(zip_filename))])

    @http.route('/web/binary/nfe_danfe/download_document', type='http', auth="user")
    def download_danfe_document(self, tab_id, **kw):
        new_tab = ast.literal_eval(tab_id)
        attachment_ids = request.env['ir.attachment'].search([('id', 'in', new_tab)])
        file_dict = {}
        for attachment_id in attachment_ids:
            file_store = attachment_id.store_fname
            if file_store:
                file_name = attachment_id.name
                file_path = attachment_id._full_path(file_store)
                file_dict["%s:%s" % (file_store, file_name)] = dict(path=file_path, name=file_name)
        zip_filename = datetime.now()
        zip_filename = "%s.zip" % zip_filename
        bitIO = BytesIO()
        zip_file = zipfile.ZipFile(bitIO, "w", zipfile.ZIP_DEFLATED)
        for file_info in file_dict.values():
            zip_file.write(file_info["path"], file_info["name"])
        zip_file.close()
        return request.make_response(bitIO.getvalue(),
                                     headers=[('Content-Type', 'application/x-zip-compressed'),
                                              ('Content-Disposition', content_disposition(zip_filename))])
