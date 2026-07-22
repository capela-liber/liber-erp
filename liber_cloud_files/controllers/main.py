# -*- coding: utf-8 -*-
import mimetypes

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request


class LiberCloudController(http.Controller):
    """The streaming door, for providers without temporary links.

    Dropbox hands the browser a four-hour URL; Drive and GitHub do not,
    so the bytes come through Odoo -- which is exactly where the gate is:
    the record rules and the folder ACL are checked before a single byte
    moves, and the provider credential never leaves the server.
    """

    @http.route('/liber_cloud/download/<int:file_id>',
                type='http', auth='user')
    def download(self, file_id, **kwargs):
        record = request.env['liber.cloud.file'].browse(file_id).exists()
        if not record:
            raise NotFound()
        record.check_access('read')          # ACL + record rules, as user
        record.folder_id._ensure_access('read')  # the folder gate, again
        data = record.folder_id._client().download(record)
        mimetype = mimetypes.guess_type(record.name)[0] \
            or 'application/octet-stream'
        return request.make_response(data, headers=[
            ('Content-Type', mimetype),
            ('Content-Length', len(data)),
            ('Content-Disposition',
             http.content_disposition(record.name, disposition_type='inline')),
        ])
