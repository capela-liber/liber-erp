# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields, models, _

from ..services.dropbox_api import DropboxClient


class LiberDropboxFile(models.Model):
    """A file Dropbox holds; Odoo keeps the metadata and opens the doors.

    No byte is stored here. Download goes through a temporary link that
    Dropbox expires after four hours; sharing creates the permanent public
    link and records who asked for it, because a shared link is the one
    thing that escapes Odoo's gate.
    """
    _name = 'liber.dropbox.file'
    _description = 'Dropbox File'
    _order = 'name'

    folder_id = fields.Many2one(
        'liber.dropbox.folder', required=True, index=True,
        ondelete='cascade')
    name = fields.Char(required=True)
    path = fields.Char(required=True, readonly=True)
    size = fields.Integer(readonly=True)
    rev = fields.Char(readonly=True)
    content_hash = fields.Char(
        readonly=True,
        help="Dropbox's own block-wise hash, not a plain sha256; equal "
             "hashes mean equal content.")
    client_modified = fields.Datetime(string='Last Modified', readonly=True)
    thumbnail = fields.Image(
        max_width=256, max_height=256, readonly=True, copy=False,
        help="Small preview rendered by Dropbox during sync; the only "
             "bytes of the file that ever enter Odoo.")
    # The bridge to the rest of the house: a contract points at its authors,
    # a cover at the book. Editable by whoever holds the folder's write ACL
    # (record rule); everything else on this model stays sync-owned.
    partner_ids = fields.Many2many(
        'res.partner', 'liber_dropbox_file_partner_rel',
        'file_id', 'partner_id', string='Contacts',
        help="The people or companies this file is about -- all the "
             "authors of the contract, the supplier of the quote.")
    product_tmpl_id = fields.Many2one(
        'product.template', string='Product', index='btree_not_null',
        help="The title this file belongs to -- its cover, its contract, "
             "its print files.")
    tag_ids = fields.Many2many(
        'liber.dropbox.tag', 'liber_dropbox_file_tag_rel',
        'file_id', 'tag_id', string='Tags')
    shared_link = fields.Char(
        readonly=True, copy=False,
        help="Public Dropbox link. Anyone holding it reaches the file "
             "without Odoo -- create it knowingly.")
    shared_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    shared_on = fields.Datetime(readonly=True, copy=False)
    share_expires = fields.Datetime(
        readonly=True, copy=False,
        help="Dropbox kills the link at this moment; sharing the file "
             "again renews the deadline.")
    active = fields.Boolean(default=True)

    def action_download(self):
        """Open a four-hour temporary link; the ACL is checked at the door."""
        self.ensure_one()
        self.folder_id._ensure_dropbox_access('read')
        link = DropboxClient(self.env).get_temporary_link(self.path)
        return {'type': 'ir.actions.act_url', 'url': link, 'target': 'new'}

    def action_share(self):
        """Create (or renew) the public shared link and sign the ledger."""
        self.ensure_one()
        self.folder_id._ensure_dropbox_access('write')
        ttl_days = int(self.env['ir.config_parameter'].sudo().get_param(
            'liber_dropbox.share_ttl_days', '30') or 0)
        expires = ttl_days and (
            fields.Datetime.now() + timedelta(days=ttl_days)) or False
        url = DropboxClient(self.env).create_shared_link(
            self.path, expires=expires or None)
        # Users hold no write ACL on this model; the ledger entry is the
        # one sanctioned write, done after the explicit gate check above.
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
