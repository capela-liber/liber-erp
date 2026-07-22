# -*- coding: utf-8 -*-
import json
import logging

import requests

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.liber_cloud_files.services.provider import wants_thumbnail

_logger = logging.getLogger(__name__)

TOKEN_URL = 'https://api.dropboxapi.com/oauth2/token'
API_URL = 'https://api.dropboxapi.com/2'
CONTENT_URL = 'https://content.dropboxapi.com/2'
TIMEOUT = 60


class DropboxClient:
    """The Dropbox implementation of the Cloud Files client contract.

    One client per operation: the short-lived access token minted from the
    refresh token lives on the instance and is never stored. Credentials
    come from the company's cloud account, so each company acts through
    its own Dropbox -- and Odoo decides who acts through it.
    """
    supports_expiration = True  # on paid Dropbox plans

    def __init__(self, account):
        self._app_key = account.dropbox_app_key
        self._app_secret = account.dropbox_app_secret
        self._refresh_token = account.dropbox_refresh_token
        self._access_token = None
        if not (self._app_key and self._app_secret and self._refresh_token):
            raise UserError(_(
                "The Dropbox account of %s is not configured. Fill in the "
                "app key, app secret and refresh token (see the module's "
                "NOTES.md for the one-time setup).",
                account.company_id.name))

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

    def _content_call(self, endpoint, arg, data=None, raw=False):
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
        return resp.content if raw else resp.json()

    @staticmethod
    def _to_datetime(value):
        return value and value.replace('T', ' ').rstrip('Z') or False

    # ------------------------------------------------------------------
    # the contract
    # ------------------------------------------------------------------
    def check(self):
        account = self._call('/users/get_current_account')
        return {'name': account.get('name', {}).get('display_name', '?'),
                'email': account.get('email', '?')}

    def list_folder(self, folder, exclude=None):
        # Dropbox nests by path, so mapped subtrees are excluded by their
        # path prefix (paths are case-insensitive there, hence lower()).
        excluded = tuple(
            f.path.lower() + '/' for f in (exclude or [])
            if f.path.lower().startswith(folder.path.lower() + '/'))
        entries = []
        result = self._call('/files/list_folder', {
            'path': folder.path, 'recursive': folder.recursive,
            'include_deleted': False, 'limit': 500,
        })
        while True:
            for entry in result['entries']:
                if entry.get('.tag') != 'file':
                    continue
                path = entry['path_display']
                if excluded and path.lower().startswith(excluded):
                    continue
                entries.append({
                    'name': entry['name'],
                    'path': path,
                    'external_id': entry.get('id'),
                    'size': entry.get('size', 0),
                    'rev': entry.get('rev'),
                    'content_hash': entry.get('content_hash'),
                    'client_modified': self._to_datetime(
                        entry.get('client_modified')),
                })
            if not result.get('has_more'):
                return entries
            result = self._call('/files/list_folder/continue',
                                {'cursor': result['cursor']})

    def temporary_link(self, file):
        """A direct download URL that Dropbox expires after four hours."""
        return self._call('/files/get_temporary_link',
                          {'path': file.path})['link']

    def download(self, file):
        # Only reached if temporary_link() is bypassed; kept for the
        # contract's completeness.
        return self._content_call('/files/download', {'path': file.path},
                                  raw=True)

    def upload(self, folder, filename, data):
        """Upload bytes, never overwriting silently (autorename)."""
        return self._content_call('/files/upload', {
            'path': f'{folder.path}/{filename}',
            'mode': 'add', 'autorename': True, 'mute': True,
        }, data=data)

    def create_shared_link(self, file, expires=None):
        """Create (or refresh) the public shared link.

        Dropbox only honours link expiration on paid plans; on a free
        plan it answers settings_error, surfaced as a clear message
        rather than silently minting an eternal link.
        """
        settings = {}
        if expires:
            settings['expires'] = expires.strftime('%Y-%m-%dT%H:%M:%SZ')
        payload = {'path': file.path}
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
                    "plan, or set the period to 0 on the account to "
                    "create links that never expire.")) from exc
            # Dropbox answers 409 when the link already exists; fetch it
            # instead of failing -- re-sharing must be idempotent.
            if 'shared_link_already_exists' not in str(exc):
                raise
        result = self._call('/sharing/list_shared_links',
                            {'path': file.path, 'direct_only': True})
        links = result.get('links')
        if not links:
            raise UserError(_(
                "Dropbox reported an existing shared link for %s but did "
                "not return it.", file.path))
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
                        "plan, or set the period to 0 on the account to "
                        "create links that never expire.")) from exc
                raise
        return url

    def get_thumbnail_batch(self, files, size='w256h256'):
        """Return {path: base64 jpeg} for what Dropbox could render."""
        paths = [f.path for f in files if wants_thumbnail(f.name)]
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
