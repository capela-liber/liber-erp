# -*- coding: utf-8 -*-
import base64
import json
import logging

import requests

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.liber_cloud_files.services.provider import wants_thumbnail

_logger = logging.getLogger(__name__)

TOKEN_URL = 'https://oauth2.googleapis.com/token'
API_URL = 'https://www.googleapis.com/drive/v3'
UPLOAD_URL = 'https://www.googleapis.com/upload/drive/v3'
FOLDER_MIME = 'application/vnd.google-apps.folder'
TIMEOUT = 60


class GDriveClient:
    """The Google Drive implementation of the Cloud Files client contract.

    Drive addresses everything by ID: the mapped folder carries its Drive
    ID in the External ID field, files carry theirs, and display paths
    are rebuilt during the walk. Drive has no anonymous temporary links,
    so downloads stream through Odoo -- which is where the gate is anyway.
    """
    supports_expiration = True  # on paid Workspace editions

    def __init__(self, account):
        self._client_id = account.gdrive_client_id
        self._client_secret = account.gdrive_client_secret
        self._refresh_token = account.gdrive_refresh_token
        self._access_token = None
        if not (self._client_id and self._client_secret
                and self._refresh_token):
            raise UserError(_(
                "The Google Drive account of %s is not configured. Fill "
                "in the client ID, client secret and refresh token (see "
                "the module's NOTES.md for the one-time setup).",
                account.company_id.name))

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------
    def _token(self):
        if self._access_token:
            return self._access_token
        try:
            resp = requests.post(TOKEN_URL, data={
                'grant_type': 'refresh_token',
                'refresh_token': self._refresh_token,
                'client_id': self._client_id,
                'client_secret': self._client_secret,
            }, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise UserError(
                _("Could not reach Google Drive: %s", exc)) from exc
        if resp.status_code != 200:
            raise UserError(_(
                "Google refused the credentials (HTTP %(code)s): %(body)s",
                code=resp.status_code, body=resp.text[:500]))
        self._access_token = resp.json()['access_token']
        return self._access_token

    def _request(self, method, url, *, raw=False, **kwargs):
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f'Bearer {self._token()}'
        try:
            resp = requests.request(
                method, url, headers=headers, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            raise UserError(
                _("Could not reach Google Drive: %s", exc)) from exc
        if resp.status_code not in (200, 204):
            raise UserError(_(
                "Google Drive call failed (HTTP %(code)s): %(body)s",
                code=resp.status_code, body=resp.text[:500]))
        return resp.content if raw else (resp.json() if resp.content else {})

    @staticmethod
    def _to_datetime(value):
        # '2026-07-22T15:00:00.123Z' -> '2026-07-22 15:00:00'
        return value and value[:19].replace('T', ' ') or False

    # ------------------------------------------------------------------
    # the contract
    # ------------------------------------------------------------------
    def check(self):
        about = self._request('GET', f'{API_URL}/about',
                              params={'fields': 'user'})
        user = about.get('user', {})
        return {'name': user.get('displayName', '?'),
                'email': user.get('emailAddress', '?')}

    def list_folder(self, folder, exclude=None):
        if not folder.external_id:
            raise UserError(_(
                "Drive folders are addressed by ID: open the folder in "
                "the browser and copy the ID from its URL into the "
                "folder's External ID field."))
        # A subtree mapped on its own is skipped by its Drive ID: the wide
        # mapping must not leak what the strict one protects.
        excluded_ids = {f.external_id for f in (exclude or [])
                        if f.external_id}
        entries = []
        queue = [(folder.external_id, folder.path)]
        while queue:
            parent_id, prefix = queue.pop(0)
            token = None
            while True:
                params = {
                    'q': f"'{parent_id}' in parents and trashed = false",
                    'fields': 'nextPageToken, files(id, name, mimeType, '
                              'size, md5Checksum, modifiedTime)',
                    'pageSize': 1000,
                }
                if token:
                    params['pageToken'] = token
                result = self._request('GET', f'{API_URL}/files',
                                       params=params)
                for item in result.get('files', []):
                    if item['mimeType'] == FOLDER_MIME:
                        if folder.recursive \
                                and item['id'] not in excluded_ids:
                            queue.append(
                                (item['id'], f"{prefix}/{item['name']}"))
                        continue
                    entries.append({
                        'name': item['name'],
                        'path': f"{prefix}/{item['name']}",
                        'external_id': item['id'],
                        'size': int(item.get('size') or 0),
                        'rev': item.get('md5Checksum')
                            or item.get('modifiedTime'),
                        'content_hash': item.get('md5Checksum'),
                        'client_modified': self._to_datetime(
                            item.get('modifiedTime')),
                    })
                token = result.get('nextPageToken')
                if not token:
                    break
        return entries

    def temporary_link(self, file):
        # Drive has no anonymous short-lived URL; the base streams the
        # download through Odoo instead.
        return None

    def download(self, file):
        return self._request(
            'GET', f'{API_URL}/files/{file.external_id}',
            params={'alt': 'media'}, raw=True)

    def upload(self, folder, filename, data):
        """Upload bytes, never overwriting silently.

        Drive happily stores two files with the same name in one folder;
        our mirror keys by path, so a name clash gets the familiar
        ' (1)' suffix instead.
        """
        filename = self._free_name(folder, filename)
        metadata = {'name': filename, 'parents': [folder.external_id]}
        body, content_type = self._multipart(metadata, data)
        return self._request(
            'POST', f'{UPLOAD_URL}/files',
            params={'uploadType': 'multipart'},
            headers={'Content-Type': content_type}, data=body)

    def _free_name(self, folder, filename):
        stem, dot, ext = filename.rpartition('.')
        candidate, counter = filename, 0
        while True:
            escaped = candidate.replace("'", "\\'")
            result = self._request('GET', f'{API_URL}/files', params={
                'q': f"'{folder.external_id}' in parents and "
                     f"name = '{escaped}' and trashed = false",
                'fields': 'files(id)', 'pageSize': 1})
            if not result.get('files'):
                return candidate
            counter += 1
            candidate = (f'{stem} ({counter}).{ext}'
                         if dot else f'{filename} ({counter})')

    @staticmethod
    def _multipart(metadata, data):
        boundary = 'liber-cloud-files-boundary'
        body = (
            f'--{boundary}\r\n'
            'Content-Type: application/json; charset=UTF-8\r\n\r\n'
            f'{json.dumps(metadata)}\r\n'
            f'--{boundary}\r\n'
            'Content-Type: application/octet-stream\r\n'
            'Content-Transfer-Encoding: base64\r\n\r\n'
        ).encode() + base64.b64encode(data) + f'\r\n--{boundary}--'.encode()
        return body, f'multipart/related; boundary={boundary}'

    def create_shared_link(self, file, expires=None):
        """Anyone-with-the-link may read; the link is the file's web view.

        Expiration on such permissions is a paid Workspace feature; the
        refusal comes back explained, never a silently eternal link.
        """
        payload = {'type': 'anyone', 'role': 'reader'}
        if expires:
            payload['expirationTime'] = expires.strftime(
                '%Y-%m-%dT%H:%M:%SZ')
        try:
            self._request(
                'POST', f'{API_URL}/files/{file.external_id}/permissions',
                json=payload)
        except UserError as exc:
            if 'expiration' in str(exc).lower():
                raise UserError(_(
                    "This Google Workspace edition does not allow links "
                    "with an expiration date. Upgrade the plan, or set "
                    "the period to 0 on the account to create links that "
                    "never expire.")) from exc
            raise
        result = self._request(
            'GET', f'{API_URL}/files/{file.external_id}',
            params={'fields': 'webViewLink'})
        return result.get('webViewLink')

    def get_thumbnail_batch(self, files):
        """Drive renders thumbnails for most formats; fetch the small ones."""
        out = {}
        for file in files:
            if not wants_thumbnail(file.name) or not file.external_id:
                continue
            try:
                meta = self._request(
                    'GET', f'{API_URL}/files/{file.external_id}',
                    params={'fields': 'thumbnailLink'})
                link = meta.get('thumbnailLink')
                if not link:
                    continue
                image = self._request('GET', link, raw=True)
                out[file.path] = base64.b64encode(image).decode()
            except UserError:
                # A missing thumbnail is not an error.
                _logger.debug("No thumbnail for %s", file.path)
        return out
