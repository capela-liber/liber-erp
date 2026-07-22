# -*- coding: utf-8 -*-
import json
import logging

import requests

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TOKEN_URL = 'https://api.dropboxapi.com/oauth2/token'
API_URL = 'https://api.dropboxapi.com/2'
CONTENT_URL = 'https://content.dropboxapi.com/2'
TIMEOUT = 60

# The formats Dropbox agrees to thumbnail; everything else (PDFs included)
# gets a plain file card and opens full-size in the browser instead.
THUMBNAIL_EXTENSIONS = (
    'jpg', 'jpeg', 'png', 'tif', 'tiff', 'gif', 'webp', 'ppm', 'bmp')


def wants_thumbnail(name):
    return ('.' in name
            and name.rsplit('.', 1)[-1].lower() in THUMBNAIL_EXTENSIONS)


class DropboxClient:
    """Thin wrapper over the Dropbox HTTP API v2.

    One client per operation: the short-lived access token minted from the
    refresh token lives on the instance and is never stored. Credentials sit
    in ir.config_parameter under the liber_dropbox.* keys, so there is a
    single Dropbox identity -- the company account -- and Odoo decides who
    may act through it (see liber.dropbox.folder ACLs).
    """

    def __init__(self, env):
        icp = env['ir.config_parameter'].sudo()
        self._app_key = icp.get_param('liber_dropbox.app_key')
        self._app_secret = icp.get_param('liber_dropbox.app_secret')
        self._refresh_token = icp.get_param('liber_dropbox.refresh_token')
        self._access_token = None
        if not (self._app_key and self._app_secret and self._refresh_token):
            raise UserError(_(
                "Dropbox is not configured. Fill in the app key, app secret "
                "and refresh token in Settings (see the module's NOTES.md "
                "for the one-time setup)."))

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------
    def _token(self):
        if self._access_token:
            return self._access_token
        try:
            resp = requests.post(
                TOKEN_URL,
                data={'grant_type': 'refresh_token',
                      'refresh_token': self._refresh_token},
                auth=(self._app_key, self._app_secret),
                timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise UserError(_("Could not reach Dropbox: %s", exc)) from exc
        if resp.status_code != 200:
            raise UserError(_(
                "Dropbox refused the credentials (HTTP %(code)s): %(body)s",
                code=resp.status_code, body=resp.text[:500]))
        self._access_token = resp.json()['access_token']
        return self._access_token

    def _call(self, endpoint, payload=None):
        """POST to an RPC endpoint (api.dropboxapi.com)."""
        try:
            resp = requests.post(
                f'{API_URL}{endpoint}',
                headers={'Authorization': f'Bearer {self._token()}',
                         'Content-Type': 'application/json'},
                data=json.dumps(payload if payload is not None else None),
                timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise UserError(_("Could not reach Dropbox: %s", exc)) from exc
        if resp.status_code != 200:
            raise UserError(_(
                "Dropbox call %(endpoint)s failed (HTTP %(code)s): %(body)s",
                endpoint=endpoint, code=resp.status_code,
                body=resp.text[:500]))
        return resp.json()

    def _content_call(self, endpoint, arg, data=None):
        """POST to a content endpoint (content.dropboxapi.com)."""
        try:
            resp = requests.post(
                f'{CONTENT_URL}{endpoint}',
                headers={'Authorization': f'Bearer {self._token()}',
                         'Dropbox-API-Arg': json.dumps(arg),
                         'Content-Type': 'application/octet-stream'},
                data=data,
                timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise UserError(_("Could not reach Dropbox: %s", exc)) from exc
        if resp.status_code != 200:
            raise UserError(_(
                "Dropbox call %(endpoint)s failed (HTTP %(code)s): %(body)s",
                endpoint=endpoint, code=resp.status_code,
                body=resp.text[:500]))
        return resp.json()

    # ------------------------------------------------------------------
    # operations
    # ------------------------------------------------------------------
    def check(self):
        """Return the account behind the token; the 'Test Connection' button."""
        return self._call('/users/get_current_account')

    def list_folder(self, path, recursive=False):
        """Return every file entry under path (cursor-paginated)."""
        entries = []
        result = self._call('/files/list_folder', {
            'path': path, 'recursive': recursive,
            'include_deleted': False, 'limit': 500,
        })
        while True:
            entries.extend(
                e for e in result['entries'] if e.get('.tag') == 'file')
            if not result.get('has_more'):
                return entries
            result = self._call('/files/list_folder/continue',
                                {'cursor': result['cursor']})

    def get_temporary_link(self, path):
        """A direct download URL that Dropbox expires after four hours."""
        return self._call('/files/get_temporary_link', {'path': path})['link']

    def upload(self, path, data):
        """Upload bytes to path, never overwriting silently (autorename)."""
        return self._content_call('/files/upload', {
            'path': path, 'mode': 'add', 'autorename': True, 'mute': True,
        }, data=data)

    def get_thumbnail_batch(self, paths, size='w256h256'):
        """Return {path: base64 jpeg} for the paths Dropbox could render.

        Paths it cannot render (too large, odd format) are silently absent
        from the result -- a missing thumbnail is not an error.
        """
        out = {}
        for start in range(0, len(paths), 25):  # API cap per batch
            chunk = paths[start:start + 25]
            try:
                resp = requests.post(
                    f'{CONTENT_URL}/files/get_thumbnail_batch',
                    headers={'Authorization': f'Bearer {self._token()}',
                             'Content-Type': 'application/json'},
                    data=json.dumps({'entries': [
                        {'path': p, 'format': 'jpeg', 'size': size,
                         'mode': 'strict'} for p in chunk]}),
                    timeout=TIMEOUT)
            except requests.RequestException as exc:
                raise UserError(
                    _("Could not reach Dropbox: %s", exc)) from exc
            if resp.status_code != 200:
                raise UserError(_(
                    "Dropbox call %(endpoint)s failed (HTTP %(code)s): "
                    "%(body)s", endpoint='/files/get_thumbnail_batch',
                    code=resp.status_code, body=resp.text[:500]))
            for path, entry in zip(chunk, resp.json()['entries']):
                if entry.get('.tag') == 'success':
                    out[path] = entry['thumbnail']
        return out

    def create_shared_link(self, path, expires=None):
        """Create (or refresh) the public shared link for path.

        expires is a naive UTC datetime. Dropbox only honours link
        expiration on paid plans; on a free plan it answers
        settings_error, surfaced as a clear message rather than silently
        minting an eternal link.
        """
        settings = {}
        if expires:
            settings['expires'] = expires.strftime('%Y-%m-%dT%H:%M:%SZ')
        payload = {'path': path}
        if settings:
            payload['settings'] = settings
        try:
            result = self._call(
                '/sharing/create_shared_link_with_settings', payload)
            return result['url']
        except UserError as exc:
            if 'settings_error' in str(exc):
                raise UserError(_(
                    "The Dropbox plan of the company account does not "
                    "allow links with an expiration date. Upgrade the "
                    "plan, or set the period to 0 in Settings to create "
                    "links that never expire.")) from exc
            # Dropbox answers 409 when the link already exists; fetch it
            # instead of failing -- re-sharing must be idempotent.
            if 'shared_link_already_exists' not in str(exc):
                raise
        result = self._call('/sharing/list_shared_links',
                            {'path': path, 'direct_only': True})
        links = result.get('links')
        if not links:
            raise UserError(_(
                "Dropbox reported an existing shared link for %s but did "
                "not return it.", path))
        url = links[0]['url']
        if settings:
            # Sharing again renews the deadline on the existing link.
            try:
                self._call('/sharing/modify_shared_link_settings',
                           {'url': url, 'settings': settings})
            except UserError as exc:
                if 'settings_error' in str(exc):
                    raise UserError(_(
                        "The Dropbox plan of the company account does not "
                        "allow links with an expiration date. Upgrade the "
                        "plan, or set the period to 0 in Settings to "
                        "create links that never expire.")) from exc
                raise
        return url
