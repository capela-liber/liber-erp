# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services.provider import wants_thumbnail

_logger = logging.getLogger(__name__)


class LiberCloudFolder(models.Model):
    """A storage folder that Odoo agrees to show, and to whom.

    The storages have one credential per company, so they cannot say
    "marketing reads, editorial writes". This model can: each mapped
    folder belongs to a company, names the groups that read and the
    groups that write, record rules enforce it on every query, and
    _ensure_access() enforces it again in every method that actually
    talks to the provider (record rules stop protecting anything the
    moment sudo() is involved).

    Mapping folders is an administrator's act; writing into them demands
    a write group, whoever you are.
    """
    _name = 'liber.cloud.folder'
    _description = 'Cloud Folder'
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(required=True)
    provider = fields.Selection(
        selection=[], required=True,
        help="Which storage holds this folder. Provider modules add "
             "their entry here.")
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        index=True)
    path = fields.Char(
        required=True, index=True,
        help="Display path from the account root, starting with '/'. For "
             "providers addressed by ID (Drive) or by repository (GitHub) "
             "this is the human name; the machine identity goes in the "
             "External ID.")
    external_id = fields.Char(
        string='External ID',
        help="The provider-side identity when a path is not enough: the "
             "Drive folder ID, the GitHub owner/repo. Providers that "
             "resolve by path leave it empty.")
    read_group_ids = fields.Many2many(
        'res.groups', 'liber_cloud_folder_read_group_rel',
        'folder_id', 'group_id', string='Read Access',
        help="Groups that see this folder and download its files. Leave "
             "empty to keep the folder visible to managers only.")
    write_group_ids = fields.Many2many(
        'res.groups', 'liber_cloud_folder_write_group_rel',
        'folder_id', 'group_id', string='Write Access',
        help="Groups that also upload into this folder and create shared "
             "links. Writing implies reading.")
    recursive = fields.Boolean(
        string='Include Subfolders',
        help="Sync also mirrors every subfolder, under this folder's "
             "access groups. A subfolder that is mapped on its own is "
             "skipped: its own (usually stricter) groups stay in charge.")
    file_ids = fields.One2many('liber.cloud.file', 'folder_id')
    file_count = fields.Integer(compute='_compute_file_count')
    last_sync = fields.Datetime(readonly=True, copy=False)
    active = fields.Boolean(default=True)

    _path_uniq = models.Constraint(
        'unique(provider, company_id, path)',
        'This folder is already mapped for this company.')

    @api.depends('file_ids')
    def _compute_file_count(self):
        data = self.env['liber.cloud.file']._read_group(
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
    def _account(self):
        self.ensure_one()
        account = self.env['liber.cloud.account'].sudo().search([
            ('provider', '=', self.provider),
            ('company_id', '=', self.company_id.id)], limit=1)
        if not account:
            raise UserError(_(
                "Company %(company)s has no %(provider)s account "
                "configured yet.",
                company=self.company_id.name, provider=self.provider))
        return account

    def _client(self):
        return self.env['liber.cloud.provider']._client(self._account())

    def _ensure_access(self, mode):
        """Raise unless the current user holds this folder's ACL for mode.

        Called before every provider operation. The check is deliberate
        and explicit here because those operations run partly under
        sudo() (users cannot write file records), and sudo() walks
        straight through record rules.

        The provider's managers (and administrators) bypass only the READ
        side. Writing into the storage -- upload, shared link -- demands
        membership in a write group, whoever you are: configuring the
        shelf is one power, filling it is another.
        """
        self.ensure_one()
        if self.env.su:
            return
        # v19 keeps res.groups readable by admins only; comparing ACLs is
        # an internal permission check, so it may (and must) read as sudo.
        folder = self.sudo()
        if mode == 'read':
            manager_group = self.env['liber.cloud.provider']._manager_group(
                folder.provider)
            if self.env.user.has_group(manager_group):
                return
            allowed = folder.read_group_ids | folder.write_group_ids
        else:
            allowed = folder.write_group_ids
        if not (allowed & self.env.user.sudo().all_group_ids):
            raise AccessError(_(
                "You do not have %(mode)s access to the folder "
                "%(folder)s.", mode=mode, folder=self.display_name))

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def action_sync(self):
        """Re-read the folder from its storage and mirror its file list.

        The mirror is metadata only -- name, size, revision -- so syncing
        is cheap and no byte is duplicated into Odoo (thumbnails aside).
        """
        File = self.env['liber.cloud.file'].sudo()
        for folder in self:
            folder._ensure_access('read')
            client = folder._client()
            # Subtrees mapped on their own keep their own ACL: the wide
            # mapping must not leak what the strict one protects. The
            # client knows how its provider nests, so it does the skipping.
            siblings = self.sudo().with_context(active_test=False).search([
                ('id', '!=', folder.id),
                ('provider', '=', folder.provider),
                ('company_id', '=', folder.company_id.id)])
            entries = client.list_folder(folder, exclude=siblings)
            known = {f.path: f for f in File.with_context(
                active_test=False).search([('folder_id', '=', folder.id)])}
            seen = set()
            thumb_wanted = File.browse()
            for entry in entries:
                path = entry['path']
                seen.add(path)
                values = {
                    'name': entry['name'],
                    'external_id': entry.get('external_id'),
                    'size': entry.get('size', 0),
                    'rev': entry.get('rev'),
                    'content_hash': entry.get('content_hash'),
                    'client_modified': entry.get('client_modified') or False,
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
                thumbs = client.get_thumbnail_batch(thumb_wanted)
                for record in thumb_wanted:
                    if record.path in thumbs:
                        record.thumbnail = thumbs[record.path]
            # A file gone from the storage stays visible nowhere, but its
            # record (and its shared-link history) is kept, archived.
            gone = [f.id for p, f in known.items() if p not in seen]
            if gone:
                File.browse(gone).write({'active': False})
            folder.sudo().last_sync = fields.Datetime.now()
        return True

    @api.model
    def _cron_sync(self):
        """Nightly mirror of every active folder, company by company.

        One folder failing (renamed upstream, credential hiccup) must not
        starve the others: log and move on. The manual Sync button stays
        for when someone cannot wait until tomorrow.
        """
        for folder in self.search([]):
            try:
                folder.with_company(folder.company_id).action_sync()
            except Exception:
                _logger.exception(
                    "Daily cloud sync failed for %s (%s)",
                    folder.path, folder.provider)

    def action_open_files(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'liber_cloud_files.action_liber_cloud_file')
        action['domain'] = [('folder_id', '=', self.id)]
        action['context'] = {'default_folder_id': self.id}
        return action
