# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _


class LiberCloudFile(models.Model):
    """A file a storage holds; Odoo keeps the metadata and opens the doors.

    No byte is stored here (thumbnails aside). Download goes through a
    temporary link when the provider offers one, or streams through Odoo
    otherwise; sharing creates the provider's link and records who asked
    for it, because a shared link is the one thing that escapes the gate.
    """
    _name = 'liber.cloud.file'
    _description = 'Cloud File'
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

    def action_download(self):
        """Open the file: direct provider link when one exists, else
        streamed through Odoo -- the ACL is checked at the door either way."""
        self.ensure_one()
        self.folder_id._ensure_access('read')
        link = self.folder_id._client().temporary_link(self)
        if not link:
            link = '/liber_cloud/download/%d' % self.id
        return {'type': 'ir.actions.act_url', 'url': link, 'target': 'new'}

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
