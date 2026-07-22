# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from ..services.dropbox_api import DropboxClient, wants_thumbnail

_logger = logging.getLogger(__name__)


class LiberDropboxFolder(models.Model):
    """A Dropbox folder that Odoo agrees to show, and to whom.

    Dropbox has one credential -- the company account -- so it cannot say
    "marketing reads, editorial writes". This model can: each mapped folder
    names the groups that read and the groups that write, record rules
    enforce it on every query, and _ensure_dropbox_access() enforces it
    again in every method that actually talks to the API (record rules stop
    protecting anything the moment sudo() is involved).
    """
    _name = 'liber.dropbox.folder'
    _description = 'Dropbox Folder'
    _order = 'name'

    name = fields.Char(required=True)
    path = fields.Char(
        required=True, index=True,
        help="Dropbox path from the account root, e.g. /Editorial/Covers.")
    read_group_ids = fields.Many2many(
        'res.groups', 'liber_dropbox_folder_read_group_rel',
        'folder_id', 'group_id', string='Read Access',
        help="Groups that see this folder and download its files. Leave "
             "empty to keep the folder visible to managers only.")
    write_group_ids = fields.Many2many(
        'res.groups', 'liber_dropbox_folder_write_group_rel',
        'folder_id', 'group_id', string='Write Access',
        help="Groups that also upload into this folder and create shared "
             "links. Writing implies reading.")
    recursive = fields.Boolean(
        string='Include Subfolders',
        help="Sync also mirrors every subfolder, under this folder's "
             "access groups. A subfolder that is mapped on its own is "
             "skipped: its own (usually stricter) groups stay in charge.")
    file_ids = fields.One2many('liber.dropbox.file', 'folder_id')
    file_count = fields.Integer(compute='_compute_file_count')
    last_sync = fields.Datetime(readonly=True, copy=False)
    active = fields.Boolean(default=True)

    _path_uniq = models.Constraint(
        'unique(path)', 'This Dropbox folder is already mapped.')

    @api.depends('file_ids')
    def _compute_file_count(self):
        data = self.env['liber.dropbox.file']._read_group(
            [('folder_id', 'in', self.ids)], ['folder_id'], ['__count'])
        counts = {folder.id: count for folder, count in data}
        for record in self:
            record.file_count = counts.get(record.id, 0)

    @api.constrains('path')
    def _check_path(self):
        for record in self:
            if not record.path.startswith('/') or record.path.endswith('/'):
                raise ValidationError(_(
                    "The path must start with '/' and not end with one, "
                    "e.g. /Editorial/Covers."))

    # ------------------------------------------------------------------
    # the gate
    # ------------------------------------------------------------------
    def _ensure_dropbox_access(self, mode):
        """Raise unless the current user holds this folder's ACL for mode.

        Called before every API operation. The check is deliberate and
        explicit here because those operations run partly under sudo()
        (users cannot write file records), and sudo() walks straight
        through record rules.

        Managers (and administrators) bypass only the READ side. Writing
        into Dropbox -- upload, shared link -- demands membership in a
        write group, whoever you are: configuring the shelf is one power,
        filling it is another.
        """
        self.ensure_one()
        if self.env.su:
            return
        # v19 keeps res.groups readable by admins only; comparing ACLs is an
        # internal permission check, so it may (and must) read them as sudo.
        folder = self.sudo()
        if mode == 'read':
            if self.env.user.has_group(
                    'liber_dropbox.group_liber_dropbox_manager'):
                return
            allowed = folder.read_group_ids | folder.write_group_ids
        else:
            allowed = folder.write_group_ids
        if not (allowed & self.env.user.sudo().all_group_ids):
            raise AccessError(_(
                "You do not have %(mode)s access to the Dropbox folder "
                "%(folder)s.", mode=mode, folder=self.display_name))

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def action_sync(self):
        """Re-read the folder from Dropbox and mirror its file list.

        The mirror is metadata only -- name, size, revision -- so syncing is
        cheap and no byte is duplicated into Odoo.
        """
        client = DropboxClient(self.env)
        File = self.env['liber.dropbox.file'].sudo()
        for folder in self:
            folder._ensure_dropbox_access('read')
            entries = client.list_folder(folder.path,
                                         recursive=folder.recursive)
            # A subtree mapped on its own keeps its own ACL: the wide
            # mapping must not leak what the strict one protects.
            # Dropbox paths are case-insensitive, hence the lower().
            excluded = ()
            if folder.recursive:
                nested = self.sudo().with_context(
                    active_test=False).search([('id', '!=', folder.id)])
                excluded = tuple(
                    f.path.lower() + '/' for f in nested
                    if f.path.lower().startswith(folder.path.lower() + '/'))
            known = {f.path: f for f in File.with_context(
                active_test=False).search([('folder_id', '=', folder.id)])}
            seen = set()
            thumb_wanted = File.browse()
            for entry in entries:
                path = entry['path_display']
                if excluded and path.lower().startswith(excluded):
                    continue
                seen.add(path)
                values = {
                    'name': entry['name'],
                    'size': entry.get('size', 0),
                    'rev': entry.get('rev'),
                    'content_hash': entry.get('content_hash'),
                    'client_modified': entry.get(
                        'client_modified', '').replace('T', ' ').rstrip('Z')
                        or False,
                }
                if path in known:
                    record = known[path]
                    stale = record.rev != values['rev']
                    record.write(values)
                    if wants_thumbnail(record.name) and (
                            stale or not record.thumbnail):
                        thumb_wanted |= record
                else:
                    record = File.create(
                        {'folder_id': folder.id, 'path': path, **values})
                    if wants_thumbnail(record.name):
                        thumb_wanted |= record
            if thumb_wanted:
                thumbs = client.get_thumbnail_batch(thumb_wanted.mapped('path'))
                for record in thumb_wanted:
                    if record.path in thumbs:
                        record.thumbnail = thumbs[record.path]
            # A file gone from Dropbox stays visible nowhere, but its
            # record (and its shared-link history) is kept, archived.
            gone = [f.id for p, f in known.items() if p not in seen]
            if gone:
                File.browse(gone).write({'active': False})
            folder.sudo().last_sync = fields.Datetime.now()
        return True

    @api.model
    def _cron_sync(self):
        """Nightly mirror of every active folder.

        One folder failing (renamed in Dropbox, token hiccup) must not
        starve the others: log and move on. The manual Sync button stays
        for when someone cannot wait until tomorrow.
        """
        for folder in self.search([]):
            try:
                folder.action_sync()
            except Exception:
                _logger.exception(
                    "Daily Dropbox sync failed for %s", folder.path)

    def action_open_files(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'liber_dropbox.action_liber_dropbox_file')
        action['domain'] = [('folder_id', '=', self.id)]
        action['context'] = {'default_folder_id': self.id}
        return action
