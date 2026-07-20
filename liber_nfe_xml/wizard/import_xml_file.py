# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
import xml.etree.ElementTree as ET
import zipfile
import base64
import io

_logger = logging.getLogger(__name__)


class ImportXMLWizard(models.TransientModel):
    _name = 'import.xml.file'
    _description = "Import XML File"

    # Multi-file upload: one or more ZIP archives at once.
    attachment_ids = fields.Many2many(
        'ir.attachment', 'import_xml_file_attachment_rel', 'wizard_id',
        'attachment_id', string='ZIP Files')
    # Kept for backward compatibility / single-file uploads.
    file = fields.Binary('File')
    file_name = fields.Char()
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, domain="[('id', 'in', allowed_company_ids)]", required=True)

    def import_xml_file(self):
        Panel = self.env['nfe.xml.panel'].sudo()
        for xml in self:
            # Accept one or more ZIP files (attachment_ids), falling back to the
            # single 'file' field.
            zip_blobs = [att.datas for att in xml.attachment_ids if att.datas]
            if not zip_blobs and xml.file:
                zip_blobs = [xml.file]
            if not zip_blobs:
                raise UserError(_("Please attach at least one ZIP file to import."))
            for blob in zip_blobs:
                xml._import_zip(base64.decodebytes(blob), Panel)

    def _import_zip(self, decoded_zip_file, Panel):
        """Import every XML in a single ZIP archive (two-pass)."""
        try:
            zip_file = zipfile.ZipFile(io.BytesIO(decoded_zip_file), 'r')
        except zipfile.BadZipFile:
            raise UserError(_("One of the uploaded files is not a valid ZIP archive."))
        try:
            with zip_file:
                file_names = [f for f in zip_file.namelist() if f.endswith('.xml')]
                # Event XMLs (procEventoNFe: cancellations, correction
                # letters) carry no emit/dest/items. Collect the
                # cancellations and apply them on a second pass, after the
                # NFe documents they refer to have been imported.
                cancellation_events = []
                for file in file_names:
                    xml_file = zip_file.read(file)
                    file_name = str(file).split('/')[-1]

                    event_info = Panel.parse_nfe_event(xml_file)
                    if event_info:
                        if event_info.get('tp_evento') in Panel.NFE_CANCEL_EVENTS:
                            cancellation_events.append((file_name, xml_file))
                        # Non-cancellation events (correction letters) skipped.
                        continue

                    # Manual upload keeps filing under the company the user
                    # picked in the wizard (they are looking at the ZIP and
                    # know what it is); automated adapters must derive it from
                    # the XML instead - see Panel._company_from_xml.
                    nfe_xml_id = Panel._ingest_xml(
                        xml_file, file_name, company=self.company_id,
                        source='manual')
                    if nfe_xml_id:
                        _logger.info('4 ----- NFe XML Created ---- %s', nfe_xml_id)

                # Second pass: store cancellations and flag the NFe records.
                for file_name, xml_file in cancellation_events:
                    event = Panel.register_cancellation_event(
                        xml_file, file_name=file_name, company_id=self.company_id.id)
                    _logger.info('5 ----- NFe Cancellation registered ---- %s', event)
        except UserError:
            raise
        except Exception as e:
            raise UserError(str(e) or _("Error importing XML file."))

    def get_root(self, xml_file):
        # LAB FORK / Odoo 19: parse in memory (the temp-file version never
        # flushed before parsing).
        return ET.fromstring(xml_file)
