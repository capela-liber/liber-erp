# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _

from ..exceptions import CloudFileGone


class LiberCloudFile(models.Model):
    """A file a storage holds; Odoo keeps the metadata and opens the doors.

    No byte is stored here (thumbnails aside). Download goes through a
    temporary link when the provider offers one, or streams through Odoo
    otherwise; sharing creates the provider's link and records who asked
    for it, because a shared link is the one thing that escapes the gate.
    """
    _name = 'liber.cloud.file'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Cloud File'
    # Talking about a file is not editing it: whoever sees it may comment,
    # e-mail and schedule activities on it. The record itself stays
    # sync-owned, and its write rule (the folder's write ACL) is untouched.
    _mail_post_access = 'read'
    _order = 'name'
    _check_company_auto = True

    folder_id = fields.Many2one(
        'liber.cloud.folder', required=True, index=True, ondelete='cascade')
    provider = fields.Selection(
        related='folder_id.provider', store=True)
    company_id = fields.Many2one(
        related='folder_id.company_id', store=True, index=True)
    name = fields.Char(required=True)
    path = fields.Char(required=True, readonly=True)
    external_id = fields.Char(readonly=True)
    size = fields.Integer(readonly=True)
    rev = fields.Char(readonly=True)
    content_hash = fields.Char(
        readonly=True,
        help="The provider's own content fingerprint; equal hashes mean "
             "equal content within the same provider.")
    client_modified = fields.Datetime(string='Last Modified', readonly=True)
    thumbnail = fields.Image(
        max_width=256, max_height=256, readonly=True, copy=False,
        help="Small preview rendered by the provider during sync; the "
             "only bytes of the file that ever enter Odoo.")
    # The bridge to the rest of the house: a contract points at its
    # authors, a cover at the book. Editable by whoever holds the folder's
    # write ACL (record rule); everything else stays sync-owned.
    partner_ids = fields.Many2many(
        'res.partner', 'liber_cloud_file_partner_rel',
        'file_id', 'partner_id', string='Contacts',
        help="The people or companies this file is about -- all the "
             "authors of the contract, the supplier of the quote.")
    product_tmpl_id = fields.Many2one(
        'product.template', string='Product', index='btree_not_null',
        check_company=True,
        help="The title this file belongs to -- its cover, its contract, "
             "its print files.")
    tag_ids = fields.Many2many(
        'liber.cloud.tag', 'liber_cloud_file_tag_rel',
        'file_id', 'tag_id', string='Tags')
    shared_link = fields.Char(
        readonly=True, copy=False,
        help="The provider's shared link. What it opens for depends on "
             "the provider -- public for Dropbox and Drive, restricted "
             "to the repository's members for GitHub.")
    shared_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    shared_on = fields.Datetime(readonly=True, copy=False)
    share_expires = fields.Datetime(
        readonly=True, copy=False,
        help="The provider kills the link at this moment; sharing the "
             "file again renews the deadline.")
    active = fields.Boolean(default=True)

    def message_subscribe(self, partner_ids=None, subtype_ids=None):
        """Following is talking, not editing: the core asks write to add
        someone else as follower -- which an activity assigned to a
        colleague does -- and a reader must be able to hand a task over.
        The read gate is checked here, as the user, before the sudo."""
        self.check_access('read')
        return super(LiberCloudFile, self.sudo()).message_subscribe(
            partner_ids=partner_ids, subtype_ids=subtype_ids)

    def action_download(self):
        """Open the file: direct provider link when one exists, else
        streamed through Odoo -- the ACL is checked at the door either way."""
        self.ensure_one()
        self.folder_id._ensure_access('read')
        try:
            link = self.folder_id._client().temporary_link(self)
        except CloudFileGone as gone:
            # Returned, not raised: raising would roll the archive back.
            self._mark_gone(gone)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'danger',
                    'title': _("This file is no longer in the storage"),
                    'message': self._gone_message(gone),
                    'sticky': True,
                    'next': {'type': 'ir.actions.client',
                             'tag': 'soft_reload'},
                },
            }
        if not link:
            link = '/liber_cloud/download/%d' % self.id
        return {'type': 'ir.actions.act_url', 'url': link, 'target': 'new'}

    def _gone_message(self, gone):
        self.ensure_one()
        message = _(
            "%(name)s was deleted, renamed or moved in %(provider)s after "
            "the last sync. The record has been archived; syncing the "
            "folder %(folder)s brings in its new name, if it has one.",
            name=self.name, provider=self._provider_label(),
            folder=self.folder_id.name)
        return '%s %s' % (message, gone.detail) if gone.detail else message

    def _provider_label(self):
        self.ensure_one()
        return dict(self._fields['provider']._description_selection(
            self.env)).get(self.provider, self.provider)

    def _mark_gone(self, gone):
        """Do now what the next sync would: archive the mirror of a file
        the storage no longer has -- and say why, on the file itself.

        Sudo because a reader may be the one who finds out; the gate was
        already checked on the way in, as that reader.
        """
        for record in self.sudo().filtered('active'):
            record.message_post(
                body=record._gone_message(gone),
                subtype_xmlid='mail.mt_note')
            record.active = False

    def action_share(self):
        """Create (or renew) the shared link and sign the ledger."""
        self.ensure_one()
        self.folder_id._ensure_access('write')
        account = self.folder_id._account()
        client = self.folder_id._client()
        ttl_days = account.share_ttl_days
        # A provider that cannot expire links (GitHub) says so on the
        # client; the ledger then honestly records "no deadline".
        if not getattr(client, 'supports_expiration', True):
            ttl_days = 0
        expires = ttl_days and (
            fields.Datetime.now() + timedelta(days=ttl_days)) or False
        url = client.create_shared_link(self, expires=expires or None)
        # Users hold no write ACL on the sync-owned fields; the ledger
        # entry is the one sanctioned write, after the gate check above.
        self.sudo().write({
            'shared_link': url,
            'shared_by_id': self.env.user.id,
            'shared_on': fields.Datetime.now(),
            'share_expires': expires,
        })
        if expires:
            message = _("%(url)s — the link dies on %(date)s.",
                        url=url, date=fields.Date.to_string(expires))
        else:
            message = url
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Shared link created"),
                'message': message,
                'sticky': True,
            },
        }

    def action_open_shared_link(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.shared_link,
                'target': 'new'}
