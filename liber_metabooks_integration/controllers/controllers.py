# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
import base64
import mimetypes
from odoo.http import content_disposition


class MetabooksIntegration(http.Controller):

    @http.route('/product/sizechart/size_chart/<int:product_id>', type='http', auth="public", methods=['POST', 'GET'],
                website=True)
    def preview_size_chart(self, product_id, **kw):
        product = request.env['product.template'].browse(product_id)
        try:
            if product.size_chart:
                filecontent = base64.b64decode(product.size_chart)
                filename = product.size_chart_name
                content_type = mimetypes.guess_type(filename)
                return request.make_response(
                    filecontent,
                    headers=[('Content-Type', content_type[0] or 'application/octet-stream')])
        except Exception:
            pass
        return False

    # To preview the size chart content
    @http.route('/product/sizechart/download/<int:product_id>', type='http', auth="public", methods=['POST', 'GET'],
                website=True)
    def download_size_chart(self, product_id, **kw):
        product = request.env['product.template'].browse(product_id)
        try:
            if product.size_chart:
                filecontent = base64.b64decode(product.size_chart)
                filename = product.size_chart_name
                content_type = mimetypes.guess_type(filename)
                return request.make_response(
                    filecontent,
                    headers=[('Content-Type', content_type[0] or 'application/octet-stream'),
                             ('Content-Disposition', content_disposition(filename)),
                             ])
        except Exception:
            pass
        return False
