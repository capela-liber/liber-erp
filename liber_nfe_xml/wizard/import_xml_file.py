# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
import xml.etree.ElementTree as ET
import zipfile
import base64
import io

_logger = logging.getLogger(__name__)

# How many failed file names to spell out in the result screen. The rest are
# counted; the whole list is always in the server log.
MAX_LISTED_FAILURES = 50


class ImportXMLWizard(models.TransientModel):
    _name = 'import.xml.file'
    _description = "Import XML File"

    # Multi-file upload: ZIP archives and/or loose XMLs, in any mix.
    attachment_ids = fields.Many2many(
        'ir.attachment', 'import_xml_file_attachment_rel', 'wizard_id',
        'attachment_id', string='Files (ZIP or XML)')
    # Kept for backward compatibility / single-file uploads.
    file = fields.Binary('File')
    file_name = fields.Char()
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, domain="[('id', 'in', allowed_company_ids)]", required=True)

    # The wizard reopens on itself after importing: closing a dialog with no
    # word about what happened is what made a silent failure indistinguishable
    # from a clean run.
    state = fields.Selection(
        [('upload', 'Upload'), ('done', 'Done')],
        default='upload', readonly=True)
    summary = fields.Text(readonly=True)
    failure_details = fields.Text(string='Files not imported', readonly=True)
    panel_ids = fields.Many2many('nfe.xml.panel', string='Imported notes',
                                 readonly=True)

    def import_xml_file(self):
        """Import every attached file, reporting what happened to each one."""
        Panel = self.env['nfe.xml.panel'].sudo()
        tally = self._new_tally()
        for wizard in self:
            blobs = [(att.name or _('attachment'), att.datas)
                     for att in wizard.attachment_ids if att.datas]
            if not blobs and wizard.file:
                blobs = [(wizard.file_name or _('file'), wizard.file)]
            if not blobs:
                raise UserError(_(
                    "Attach at least one file to import (a ZIP archive, "
                    "or the XML itself)."))
            for name, blob in blobs:
                wizard._import_blob(name, base64.decodebytes(blob), Panel, tally)
        return self._import_result_action(tally)

    def _new_tally(self):
        return {
            'panels': self.env['nfe.xml.panel'].browse(),
            'cancellations': 0,
            'duplicate': 0,
            'not_nfe': 0,
            'malformed': 0,
            'no_protocol': 0,
            'skipped_files': 0,   # non-XML members of an archive
            'failures': [],       # [(file_name, message)]
        }

    def _import_blob(self, name, decoded, Panel, tally):
        """Route one uploaded file: a ZIP full of XMLs, or a single XML.

        A supplier e-mailing one note sends the XML itself, not a ZIP - the
        commonest case of all, and the one the wizard used to reject outright
        with "not a valid ZIP archive".
        """
        try:
            if zipfile.is_zipfile(io.BytesIO(decoded)):
                self._import_zip(decoded, Panel, tally)
            elif decoded.lstrip()[:1] == b'<':
                self._import_one(name, decoded, Panel, tally, cancellations=None)
            else:
                tally['failures'].append(
                    (name, _("neither a ZIP archive nor an XML file")))
        except Exception as e:
            # One bad upload must not cost the user the other ones.
            _logger.exception("NFe import: unreadable upload %s", name)
            tally['failures'].append((name, str(e)))

    def _import_zip(self, decoded_zip_file, Panel, tally):
        """Import every XML in a single ZIP archive (two-pass)."""
        with zipfile.ZipFile(io.BytesIO(decoded_zip_file), 'r') as zip_file:
            members = [f for f in zip_file.namelist() if not f.endswith('/')]
            # Case-insensitive: SEFAZ portals and legacy ERPs ship '.XML', and
            # a ZIP full of those used to import zero notes without a word.
            xml_names = [f for f in members if f.lower().endswith('.xml')]
            tally['skipped_files'] += len(members) - len(xml_names)
            # Event XMLs (procEventoNFe: cancellations, correction letters)
            # carry no emit/dest/items. Collect the cancellations and apply
            # them on a second pass, after the NFe documents they refer to
            # have been imported.
            cancellations = []
            for member in xml_names:
                file_name = str(member).split('/')[-1]
                try:
                    xml_file = zip_file.read(member)
                except Exception as e:
                    tally['failures'].append((file_name, str(e)))
                    continue
                self._import_one(file_name, xml_file, Panel, tally, cancellations)
            for file_name, xml_file in cancellations:
                self._apply_cancellation(file_name, xml_file, Panel, tally)

    def _import_one(self, file_name, xml_file, Panel, tally, cancellations):
        """Import one XML, counting the outcome. Never raises.

        Each file gets its own savepoint: a single corrupt member of a
        500-file ZIP used to raise UserError and roll the whole upload back,
        throwing away every note already read in the same click.
        """
        panel = Panel.browse()
        try:
            with self.env.cr.savepoint():
                event_info = Panel.parse_nfe_event(xml_file)
                if event_info:
                    if event_info.get('tp_evento') in Panel.NFE_CANCEL_EVENTS:
                        if cancellations is None:
                            self._apply_cancellation(
                                file_name, xml_file, Panel, tally)
                        else:
                            cancellations.append((file_name, xml_file))
                    else:
                        # Correction letters carry no note to import.
                        tally['not_nfe'] += 1
                    return
                key, reason = Panel.classify_nfe_xml(xml_file)
                if not key:
                    tally[reason] += 1
                    return
                # Manual upload keeps filing under the company the user picked
                # in the wizard (they are looking at the ZIP and know what it
                # is); automated adapters must derive it from the XML instead
                # - see Panel._company_from_xml.
                panel = Panel._ingest_xml(
                    xml_file, file_name, company=self.company_id,
                    source='manual')
                # Flush inside the savepoint: a constraint that only fires on
                # flush must be caught here, not counted as a success.
                panel.flush_recordset()
        except Exception as e:
            _logger.exception("NFe import failed on %s", file_name)
            tally['failures'].append((file_name, str(e)))
            return
        if panel:
            tally['panels'] |= panel
        else:
            tally['failures'].append((file_name, _("could not be imported")))

    def _apply_cancellation(self, file_name, xml_file, Panel, tally):
        try:
            with self.env.cr.savepoint():
                event = Panel.register_cancellation_event(
                    xml_file, file_name=file_name,
                    company_id=self.company_id.id)
        except Exception as e:
            _logger.exception("NFe import: cancellation failed on %s", file_name)
            tally['failures'].append((file_name, str(e)))
            return
        if event:
            tally['cancellations'] += 1
        else:
            tally['not_nfe'] += 1

    def _import_summary(self, tally):
        """One line per outcome, in the order that matters to the user."""
        # The counts are unpacked first on purpose: a dict subscript sitting in
        # the same expression as a _() call gets swept into the translation
        # catalogue, so 'duplicate' and 'skipped_files' turned up as msgids for
        # a translator to puzzle over.
        imported = len(tally['panels'])
        cancelled = tally['cancellations']
        duplicated = tally['duplicate']
        not_nfe = tally['not_nfe']
        no_protocol = tally['no_protocol']
        malformed = tally['malformed']
        ignored = tally['skipped_files']
        failed = len(tally['failures'])
        counts = [
            (imported, _("%s note(s) imported")),
            (cancelled, _("%s cancellation(s) applied")),
            (duplicated, _("%s already in the panel")),
            (not_nfe, _("%s not an NFe")),
            (no_protocol, _("%s with no SEFAZ protocol")),
            (malformed, _("%s unreadable")),
            (ignored, _("%s non-XML file(s) ignored")),
            (failed, _("%s failed")),
        ]
        lines = [label % count for count, label in counts if count]
        return "\n".join(lines) or _("Nothing to import.")

    def _import_result_action(self, tally):
        """Reopen the wizard showing what happened, instead of closing mute."""
        failures = tally['failures']
        if failures:
            shown = failures[:MAX_LISTED_FAILURES]
            details = "\n".join("%s - %s" % (name, msg) for name, msg in shown)
            if len(failures) > len(shown):
                details += "\n" + _("... and %s more (see the server log).") % (
                    len(failures) - len(shown))
        else:
            details = False
        self.write({
            'state': 'done',
            'summary': self._import_summary(tally),
            'failure_details': details,
            'panel_ids': [(6, 0, tally['panels'].ids)],
        })
        if tally['panels']:
            # The notes land in 'imported' and are parsed by a cron that runs
            # every 10 minutes; nudge it so the panel fills in now rather than
            # leaving the user staring at raw rows.
            cron = self.env.ref('liber_nfe_xml.cron_process_nfe_xml_content',
                                raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import XML File'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_panels(self):
        """Open the notes this import created."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Imported notes'),
            'res_model': 'nfe.xml.panel',
            'domain': [('id', 'in', self.panel_ids.ids)],
            'view_mode': 'list,form',
            'context': {'create': False},
        }

    def get_root(self, xml_file):
        # LAB FORK / Odoo 19: parse in memory (the temp-file version never
        # flushed before parsing).
        return ET.fromstring(xml_file)
