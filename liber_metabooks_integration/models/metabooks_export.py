# -*- coding: utf-8 -*-
"""Sending our book data back to Metabooks, with a human in the middle.

The shape of the thing: editing a book marks it pending (product.template
below); a batch gathers what is pending, shows the before/after of every field,
and lets someone uncheck what should not go; generating produces the .xlsx with
the changed cells in red; only once the file is actually delivered do the books
stop being pending.

Nothing here talks to Metabooks. Delivery is still manual -- download the file,
upload it -- until we have their REST API credentials, at which point
_deliver() is the only method that needs a body.

The batch, its lines and their changes are kept forever: they are the record of
what we asked Metabooks to alter, and when. The books move on; this does not.
"""

import base64
import logging
from datetime import date

import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from ..services import metabooks_mapping as mapping
from ..services import metabooks_sheet as sheet

_logger = logging.getLogger(__name__)

# Which old_value_* column mail.tracking.value uses per field type.
_TRACKING_COLUMN = {
    'integer': 'integer',
    'boolean': 'integer',
    'float': 'float',
    'monetary': 'float',
    'date': 'datetime',
    'datetime': 'datetime',
    'char': 'char',
    'selection': 'char',
    'many2one': 'char',
    'many2many': 'char',
    'one2many': 'char',
    'text': 'text',
    'html': 'text',
}


_HTML = re.compile(r'<[a-zA-Z/][^>]*>')


def _plain(value):
    """Text as Metabooks wants it: no markup.

    Synopses in particular pick up HTML -- the website editor writes into the
    same field -- and their spreadsheet column is plain text, so a <div> would
    reach readers as literal markup. Only touched when the value really does
    carry a tag, so ordinary text containing a "<" survives intact.
    """
    if not isinstance(value, str) or not _HTML.search(value):
        return value
    return html2plaintext(value).strip()


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    metabooks_export_pending = fields.Boolean(
        'Pending Metabooks Export', default=False, copy=False, index=True,
        readonly=True,
        help="Set when a field Metabooks knows about is edited here, cleared "
             "once the change has been delivered to them.")
    metabooks_export_pending_since = fields.Datetime(
        'Pending Since', copy=False, readonly=True)
    metabooks_export_last = fields.Datetime(
        'Last Sent to Metabooks', copy=False, readonly=True)
    metabooks_export_last_track = fields.Integer(
        'History Cut-off', copy=False, readonly=True, default=0,
        help="Highest mail.tracking.value id at the moment of the last send. "
             "Reading the change history from here rather than from a "
             "timestamp is what keeps an edit made in the same second as a "
             "send from being lost: mail.message.date only resolves to the "
             "second, and a change that falls inside it would look older than "
             "the send that did not carry it.")

    def write(self, vals):
        res = super().write(vals)
        # An import from Metabooks writes the same fields a person does. Left
        # alone it would mark every imported book as pending and send their own
        # data straight back at them.
        if self.env.context.get('metabooks_from_sync'):
            return res
        touched = mapping.WATCHED_FIELDS.intersection(vals)
        if not touched:
            return res
        stale = self.filtered(lambda p: not p.metabooks_export_pending)
        if stale:
            stale.with_context(metabooks_from_sync=True).write({
                'metabooks_export_pending': True,
                'metabooks_export_pending_since': fields.Datetime.now(),
            })
        return res

    def action_metabooks_clear_pending(self):
        """Drop out of the queue without sending -- the change was not for them."""
        return self.with_context(metabooks_from_sync=True).write({
            'metabooks_export_pending': False,
            'metabooks_export_pending_since': False,
        })

    # ---------------------------------------------------------------- #
    #  Reading one book as Metabooks columns
    # ---------------------------------------------------------------- #

    def _metabooks_is_known(self):
        """Does Metabooks already have this title?

        Not "have we sent it before". Every book imported from them is already
        registered there, and none of them was ever sent from here -- so basing
        the new/update split on our own send history made the first update
        batch come up empty for the entire catalogue. Carrying their publisher
        id is the evidence that the title came from them.
        """
        self.ensure_one()
        return bool(self.metabooks_export_last or self.metabooks_vendor_id)

    def _metabooks_gtin(self):
        """Their dedup key. Digits only -- the guide says 'Somente números'."""
        self.ensure_one()
        raw = self.barcode or self.default_code or ''
        return ''.join(c for c in raw if c.isdigit())

    def _metabooks_cell(self, column):
        """Current value of one Metabooks column for this book, or False."""
        self.ensure_one()
        field, kind, extra = mapping.BY_COLUMN[column]
        value = self[field]

        if kind == mapping.AUTHORS:
            return self._metabooks_contributors(extra)
        if kind == mapping.BISAC:
            return ';'.join(c for c in value.mapped('bisac_code') if c) or False
        if kind == mapping.AVAILABILITY:
            return value.product_definition or False if value else False
        if kind == mapping.COUNTRY:
            return value.code or False if value else False
        if kind == mapping.M2O_NAME:
            return value.name or False if value else False
        if kind == mapping.PRICE:
            return round(value, 2) if value else False
        if kind in (mapping.INT, mapping.FLOAT):
            # Zero is how Odoo spells "never filled in" for these; sending it
            # would tell Metabooks the book weighs nothing.
            return value or False
        if kind == mapping.DATE:
            return value or False
        return _plain(value) or False

    def _metabooks_contributors(self, role_code):
        """"Silva, Augusto da; Araújo, Michele" -- surname first, "; " between."""
        self.ensure_one()
        names = []
        for author in self.book_auther_ids:
            if (author.author_contributor_role.name or '') != role_code:
                continue
            surname = (author.author_last_name or '').strip()
            given = (author.name or '').strip()
            if surname and given:
                names.append('%s, %s' % (surname, given))
            elif author.author_full_name:
                names.append(author.author_full_name.strip())
            elif surname or given:
                names.append(surname or given)
        return '; '.join(names) or False


class MetabooksExportBatch(models.Model):
    _name = 'metabooks.export.batch'
    _description = 'Metabooks Export Batch'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(
        'Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    task = fields.Selection(
        [(sheet.TASK_UPDATE, 'Alteração (V)'),
         (sheet.TASK_NEW, 'Cadastro novo (Z)'),
         (sheet.TASK_ARCHIVE, 'Arquivamento (X)'),
         (sheet.TASK_REACTIVATE, 'Reativação (R)')],
        string='Task', default=sheet.TASK_UPDATE, required=True,
        readonly=False, tracking=True,
        help="Metabooks reads this from the first letter of the file name. A "
             "file carries one task, so a batch does too.")
    state = fields.Selection(
        [('draft', 'Draft'), ('checked', 'Checked'),
         ('generated', 'Generated'), ('sent', 'Sent'), ('cancel', 'Cancelled')],
        default='draft', required=True, tracking=True)
    mb_id = fields.Char(
        'MB ID Editor', tracking=True,
        help="Publisher id at Metabooks, second part of the file name. Taken "
             "from the books when they all agree.")
    free_text = fields.Char(
        'File Name Text', default='Alteracoes',
        help="Last part of the file name. Only a human reads it.")
    line_ids = fields.One2many(
        'metabooks.export.line', 'batch_id', string='Books')
    # Flat view of every field change in the batch: the de/para screen, and
    # what comes out red in the spreadsheet.
    change_ids = fields.One2many(
        'metabooks.export.change', 'batch_id', string='Changes', readonly=True)
    selected_count = fields.Integer(compute='_compute_counts')
    change_count = fields.Integer(compute='_compute_counts')
    filename = fields.Char(readonly=True, copy=False)
    attachment_id = fields.Many2one(
        'ir.attachment', string='File', readonly=True, copy=False)
    generated_on = fields.Datetime(readonly=True, copy=False)
    generated_by = fields.Many2one('res.users', readonly=True, copy=False)
    sent_on = fields.Datetime(readonly=True, copy=False)
    sent_by = fields.Many2one('res.users', readonly=True, copy=False)
    note = fields.Text('Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'metabooks.export.batch') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.selected', 'line_ids.change_ids',
                 'line_ids.change_ids.selected')
    def _compute_counts(self):
        for batch in self:
            chosen = batch.line_ids.filtered('selected')
            batch.selected_count = len(chosen)
            batch.change_count = len(chosen.change_ids.filtered('selected'))

    # ---------------------------------------------------------------- #
    #  Gathering
    # ---------------------------------------------------------------- #

    def action_prepare(self):
        """Pull in every pending book, with its before/after.

        Replaces whatever is in the batch: this is a reload button, and the
        alternative -- merging -- makes it impossible to tell what you are
        looking at.
        """
        self.ensure_one()
        self._assert_open()
        self.line_ids.unlink()

        products = self.env['product.template'].search(
            [('metabooks_export_pending', '=', True)])
        if self.task == sheet.TASK_NEW:
            products = products.filtered(lambda p: not p._metabooks_is_known())
        elif self.task == sheet.TASK_UPDATE:
            products = products.filtered(lambda p: p._metabooks_is_known())

        if not products:
            raise UserError(_(
                "No book is waiting to be sent to Metabooks for this task."))

        for product in products:
            self._build_line(product)
        self._guess_mb_id()
        return True

    def _build_line(self, product):
        line = self.env['metabooks.export.line'].create({
            'batch_id': self.id,
            'product_id': product.id,
            'gtin': product._metabooks_gtin(),
            'title': (product.metabooks_book_title or product.name or '')[:200],
        })
        history = self._tracked_since(product, product.metabooks_export_last_track)
        columns = set()
        for field in history:
            columns.update(mapping.columns_for(field))
        # A book can be pending without usable history -- tracking added later,
        # a write that bypassed the chatter. Better to send every mapped column
        # than to send an empty row, so fall back to the whole record.
        if not columns:
            line.no_history = True
            columns = set(mapping.BY_COLUMN)

        changes = []
        for column in sorted(columns):
            field = mapping.BY_COLUMN[column][0]
            new = product._metabooks_cell(column)
            old = history.get(field, {}).get('old')
            if new is False and old is None:
                continue
            # Edited and put back: the chatter remembers the round trip, but
            # Metabooks has nothing to learn from it.
            if old is not None and self._as_text(old) == self._as_text(new):
                continue
            changes.append((0, 0, {
                'column': column,
                'field_name': field,
                'old_value': self._as_text(old),
                'new_value': self._as_text(new),
            }))
        line.change_ids = changes
        return line

    def _tracked_since(self, product, after_track_id):
        """{field name: {'old': value}} from the chatter.

        Only the oldest recorded old value matters: if a title went A -> B -> C
        since the last send, what Metabooks needs to know is that it was A and
        is now C. The new value is read live off the record rather than from
        tracking, so an edit made outside the chatter cannot make us send a
        stale one.
        """
        Tracking = self.env['mail.tracking.value']
        domain = [
            ('mail_message_id.model', '=', 'product.template'),
            ('mail_message_id.res_id', '=', product.id),
            ('field_id.name', 'in', list(mapping.WATCHED_FIELDS)),
        ]
        if after_track_id:
            domain.append(('id', '>', after_track_id))
        history = {}
        for track in Tracking.search(domain, order='id asc'):
            name = track.field_id.name
            if name in history:
                continue
            history[name] = {'old': self._tracking_old_value(track)}
        return history

    @staticmethod
    def _tracking_old_value(track):
        """Read the column mail.tracking.value stored this field in.

        Dispatch on the field type rather than taking the first non-empty
        column: a page count that went from 0 to 300 has a meaningful old value
        of zero, and scanning for truthiness would report it as blank.
        """
        suffix = _TRACKING_COLUMN.get(track.field_id.ttype)
        if suffix:
            return track['old_value_%s' % suffix]
        for suffix in ('char', 'text', 'datetime', 'float', 'integer'):
            value = track['old_value_%s' % suffix]
            if value not in (False, None, ''):
                return value
        return None

    @staticmethod
    def _as_text(value):
        if value is None:
            return ''
        if value is False:
            return ''
        if hasattr(value, 'strftime'):
            return fields.Date.to_string(value)
        return str(value)

    def _guess_mb_id(self):
        ids = {p.metabooks_vendor_id for p in self.line_ids.product_id
               if p.metabooks_vendor_id}
        if len(ids) == 1:
            self.mb_id = ids.pop()

    # ---------------------------------------------------------------- #
    #  Selecting
    # ---------------------------------------------------------------- #

    def action_select_all(self):
        self.ensure_one()
        self._assert_open()
        self.line_ids.selected = True

    def action_select_none(self):
        self.ensure_one()
        self._assert_open()
        self.line_ids.selected = False

    # ---------------------------------------------------------------- #
    #  Checking
    # ---------------------------------------------------------------- #

    def action_check(self):
        """Everything we can catch before they do, at midnight, by e-mail."""
        self.ensure_one()
        self._assert_open()
        self._raise_on_problems()
        chosen = self.line_ids.filtered('selected')
        self.state = 'checked'
        self.message_post(body=_(
            "Checked: %(books)s book(s), %(changes)s field change(s).",
            books=len(chosen), changes=len(chosen.change_ids)))
        return True

    def _raise_on_problems(self):
        problems = self._problems()
        if problems:
            raise UserError(
                _("Metabooks would reject this file:\n\n• %s")
                % '\n• '.join(problems))

    def _problems(self):
        self.ensure_one()
        chosen = self.line_ids.filtered('selected')
        if not chosen:
            raise UserError(_("Nothing is selected to send."))

        problems = []
        if not self.mb_id:
            problems.append(_("The MB ID Editor is empty; the file name needs it."))

        seen = {}
        for line in chosen:
            label = line.title or line.product_id.display_name
            if not line.gtin:
                problems.append(_("%s: no ISBN/barcode.", label))
            elif len(line.gtin) != 13:
                problems.append(_(
                    "%(book)s: ISBN %(gtin)s is not 13 digits.",
                    book=label, gtin=line.gtin))
            elif line.gtin in seen:
                problems.append(_(
                    "%(book)s and %(other)s share the ISBN %(gtin)s.",
                    book=label, other=seen[line.gtin], gtin=line.gtin))
            else:
                seen[line.gtin] = label

            if self.task in sheet.KEY_ONLY_TASKS:
                continue
            picked = line.change_ids.filtered('selected')
            if not picked:
                problems.append(_(
                    "%s: no change is ticked, so the row would be empty.",
                    label))

            # A cleared field cannot ride in the sheet: Metabooks reads a blank
            # cell as "leave this alone", and wiping one needs an explicit
            # marker ($$, -1, 11/11/1111) which we do not write yet -- and which
            # their documentation does not say every column accepts. Sending the
            # row anyway would look like the change went through when it did
            # not, so say so instead of guessing.
            cleared = [c.column for c in picked
                       if not c.new_value and c.old_value]
            if cleared:
                problems.append(_(
                    "%(book)s: %(cols)s was cleared here, and clearing a field "
                    "at Metabooks needs a deletion marker this export does not "
                    "write yet. Either put the value back, or leave this book "
                    "out of the batch and clear it in their panel.",
                    book=label, cols=', '.join(cleared)))
            if self.task == sheet.TASK_NEW:
                filled = {c.column for c in picked if c.new_value}
                missing = [c for c in sheet.MANDATORY
                           if c != sheet.KEY_COLUMN and c not in filled]
                if missing:
                    problems.append(_(
                        "%(book)s: a new title needs %(cols)s.",
                        book=label, cols=', '.join(missing)))

        return problems

    # ---------------------------------------------------------------- #
    #  Generating
    # ---------------------------------------------------------------- #

    def action_generate(self):
        self.ensure_one()
        self._assert_open()
        # Always, not only from draft: a batch checked an hour ago can have had
        # books unticked since, and the file is what actually leaves.
        self._raise_on_problems()

        chosen = self.line_ids.filtered('selected')
        rows = [line._as_row(self.task) for line in chosen]
        data = sheet.write_workbook(rows)
        name = sheet.build_filename(
            self.task, self.mb_id, date.today(), self.free_text or 'Export')

        attachment = self.env['ir.attachment'].create({
            'name': name,
            'datas': base64.b64encode(data),
            'res_model': self._name,
            'res_id': self.id,
            'type': 'binary',
        })
        self.write({
            'filename': name,
            'attachment_id': attachment.id,
            'generated_on': fields.Datetime.now(),
            'generated_by': self.env.user.id,
            'state': 'generated',
        })
        self.message_post(
            body=_("Generated %(name)s: %(books)s book(s), %(changes)s change(s).",
                   name=name, books=len(chosen), changes=len(chosen.change_ids)),
            attachment_ids=attachment.ids)
        return self.action_download()

    def action_download(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("Generate the file first."))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % self.attachment_id.id,
            'target': 'self',
        }

    # ---------------------------------------------------------------- #
    #  Delivering
    # ---------------------------------------------------------------- #

    def action_mark_sent(self):
        """Confirm the file reached Metabooks, and let the books go.

        Deliberately a separate, manual step: until _deliver() has a body,
        the upload happens outside Odoo, and only the person who did it knows
        whether it worked. Clearing the pending flag on generation instead
        would silently lose changes whenever an upload failed.
        """
        self.ensure_one()
        if self.state != 'generated':
            raise UserError(_("Generate the file before marking it as sent."))

        products = self.line_ids.filtered('selected').product_id
        now = fields.Datetime.now()
        # Everything tracked up to here is what this file carried; anything
        # recorded after it is a change we still owe them.
        cut_off = self.env['mail.tracking.value'].search(
            [], order='id desc', limit=1).id or 0
        products.with_context(metabooks_from_sync=True).write({
            'metabooks_export_pending': False,
            'metabooks_export_pending_since': False,
            'metabooks_export_last': now,
            'metabooks_export_last_track': cut_off,
        })
        self.write({'state': 'sent', 'sent_on': now, 'sent_by': self.env.user.id})
        self.message_post(body=_(
            "Marked as delivered to Metabooks: %s book(s) left the queue. "
            "Their confirmation e-mail arrives after midnight.", len(products)))
        return True

    def _deliver(self):
        """Hand the file to Metabooks.

        Empty on purpose. Their REST API documentation is not public -- the FAQ
        says to ask them for it -- so the transport is pending an answer from
        atendimentobr@mvb-online.com. FTP is documented (ftp.metabooks.com,
        passive, ports 20000-20500, folder 'upload', portal credentials) and is
        the fallback if the API turns out to be read-only.
        """
        raise UserError(_(
            "Automatic delivery is not set up yet. Download the file and "
            "upload it to Metabooks, then press Mark as Sent."))

    # ---------------------------------------------------------------- #

    def action_cancel(self):
        self.ensure_one()
        if self.state == 'sent':
            raise UserError(_("A batch that was sent cannot be cancelled."))
        self.state = 'cancel'

    def action_reset(self):
        self.ensure_one()
        if self.state == 'sent':
            raise UserError(_("A batch that was sent cannot be reopened."))
        self.state = 'draft'

    def _assert_open(self):
        if self.state in ('sent', 'cancel'):
            raise UserError(_("This batch is closed."))


class MetabooksExportLine(models.Model):
    _name = 'metabooks.export.line'
    _description = 'Metabooks Export Line'
    _order = 'title, id'

    batch_id = fields.Many2one(
        'metabooks.export.batch', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one(
        'product.template', string='Book', required=True, ondelete='restrict')
    selected = fields.Boolean(default=True)
    gtin = fields.Char('ISBN', readonly=True)
    title = fields.Char(readonly=True)
    change_ids = fields.One2many('metabooks.export.change', 'line_id')
    change_count = fields.Integer(compute='_compute_change_count')
    no_history = fields.Boolean(
        readonly=True,
        help="No chatter history was found for this book, so every mapped "
             "field is being sent rather than just what changed.")

    @api.depends('change_ids', 'change_ids.selected')
    def _compute_change_count(self):
        for line in self:
            line.change_count = len(line.change_ids.filtered('selected'))

    def _as_row(self, task):
        """One spreadsheet row: the key, an anchor, and what changed."""
        self.ensure_one()
        values = {sheet.KEY_COLUMN: self.gtin}
        changed = set()
        if task in sheet.KEY_ONLY_TASKS:
            return {'values': values, 'changed': changed}

        # The title rides along unmarked even when it did not change: a row of
        # a bare ISBN and a loose price is unreadable, and re-sending a title we
        # own is harmless.
        title = self.product_id._metabooks_cell('Título')
        if title:
            values['Título'] = title

        for change in self.change_ids.filtered('selected'):
            value = self.product_id._metabooks_cell(change.column)
            if value is False:
                continue
            values[change.column] = value
            changed.add(change.column)
        return {'values': values, 'changed': changed}


class MetabooksExportChange(models.Model):
    _name = 'metabooks.export.change'
    _description = 'Metabooks Export Change'
    _order = 'column, id'

    line_id = fields.Many2one(
        'metabooks.export.line', required=True, ondelete='cascade', index=True)
    batch_id = fields.Many2one(
        related='line_id.batch_id', store=True, index=True)
    product_id = fields.Many2one(related='line_id.product_id', store=True)
    selected = fields.Boolean(
        default=True,
        help="Untick to leave this one field out. The book still goes; the "
             "column simply is not written, and a column Metabooks does not "
             "receive is a column it leaves alone.")
    column = fields.Char('Metabooks Column', readonly=True)
    field_name = fields.Char('Odoo Field', readonly=True)
    old_value = fields.Char('Before', readonly=True)
    new_value = fields.Char('After', readonly=True)
