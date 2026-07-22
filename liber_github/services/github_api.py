# -*- coding: utf-8 -*-
import base64
from urllib.parse import quote

import requests

from odoo import _
from odoo.exceptions import UserError

API_URL = 'https://api.github.com'
TIMEOUT = 60


class GitHubClient:
    """The GitHub implementation of the Cloud Files client contract.

    A mapped "folder" is a repository (External ID = owner/repo), an
    optional subdirectory (the folder's path) and a branch. Every upload
    is a commit; the revision is the blob's SHA; and the shared link is
    the blob's page, which only opens for people who can see the
    repository -- for once, a share that does not pierce the gate.
    """
    supports_expiration = False  # a repo link has no expiry to speak of

    def __init__(self, account):
        self._token = account.github_token
        if not self._token:
            raise UserError(_(
                "The GitHub account of %s is not configured. Fill in the "
                "access token (see the module's NOTES.md).",
                account.company_id.name))

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------
    def _request(self, method, path, *, raw=False, ok=(200, 201), **kwargs):
        headers = kwargs.pop('headers', {})
        headers.setdefault('Accept', 'application/vnd.github+json')
        headers['Authorization'] = f'Bearer {self._token}'
        try:
            resp = requests.request(
                method, f'{API_URL}{path}', headers=headers,
                timeout=TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            raise UserError(_("Could not reach GitHub: %s", exc)) from exc
        if resp.status_code not in ok:
            raise UserError(_(
                "GitHub call %(path)s failed (HTTP %(code)s): %(body)s",
                path=path, code=resp.status_code, body=resp.text[:500]))
        return resp.content if raw else (resp.json() if resp.content else {})

    @staticmethod
    def _repo(folder):
        if not folder.external_id or '/' not in folder.external_id:
            raise UserError(_(
                "GitHub folders are repositories: fill in the External "
                "ID as owner/repository, e.g. capela-liber/liber-erp."))
        return folder.external_id

    def _branch(self, folder):
        if folder.github_branch:
            return folder.github_branch
        repo = self._repo(folder)
        return self._request('GET', f'/repos/{repo}')['default_branch']

    @staticmethod
    def _subdir(folder):
        return folder.path.strip('/')

    def _file_repo_path(self, file):
        # file.path is '/sub/dir/name.ext' relative to the repo root.
        return file.path.lstrip('/')

    # ------------------------------------------------------------------
    # the contract
    # ------------------------------------------------------------------
    def check(self):
        user = self._request('GET', '/user')
        return {'name': user.get('name') or user.get('login', '?'),
                'email': user.get('email') or user.get('login', '?')}

    def list_folder(self, folder, exclude=None):
        repo = self._repo(folder)
        branch = self._branch(folder)
        subdir = self._subdir(folder)
        # Subtrees mapped on their own (same repo, deeper path) keep their
        # own ACL: the wide mapping must not leak what the strict protects.
        excluded = tuple(
            f.path.strip('/') + '/' for f in (exclude or [])
            if f.external_id == folder.external_id
            and f.path.strip('/').startswith(subdir + '/' if subdir else ''))
        tree = self._request(
            'GET', f'/repos/{repo}/git/trees/{quote(branch)}',
            params={'recursive': '1'})
        entries = []
        prefix = subdir + '/' if subdir else ''
        for item in tree.get('tree', []):
            if item.get('type') != 'blob':
                continue
            path = item['path']
            if prefix and not path.startswith(prefix):
                continue
            relative = path[len(prefix):]
            if not folder.recursive and '/' in relative:
                continue
            if excluded and path.startswith(excluded):
                continue
            entries.append({
                'name': path.rsplit('/', 1)[-1],
                'path': '/' + path,
                'external_id': item['sha'],
                'size': item.get('size', 0),
                'rev': item['sha'],
                'content_hash': item['sha'],
                'client_modified': False,  # a per-file commit lookup is
                                           # an API call per file; skipped
            })
        return entries

    def temporary_link(self, file):
        # Raw URLs demand the token; the base streams through Odoo instead.
        return None

    def download(self, file):
        repo = self._repo(file.folder_id)
        branch = self._branch(file.folder_id)
        return self._request(
            'GET', f'/repos/{repo}/contents/{quote(self._file_repo_path(file))}',
            params={'ref': branch},
            headers={'Accept': 'application/vnd.github.raw'}, raw=True)

    def upload(self, folder, filename, data):
        """Every upload is a commit, and it never overwrites: a name
        clash gets the familiar ' (1)' suffix instead of a new blob on
        top of someone's file."""
        repo = self._repo(folder)
        branch = self._branch(folder)
        subdir = self._subdir(folder)
        filename = self._free_name(repo, branch, subdir, filename)
        path = f'{subdir}/{filename}' if subdir else filename
        return self._request(
            'PUT', f'/repos/{repo}/contents/{quote(path)}',
            json={
                'message': f'liber: {filename}',
                'content': base64.b64encode(data).decode(),
                'branch': branch,
            })

    def _exists(self, repo, branch, path):
        try:
            self._request('GET', f'/repos/{repo}/contents/{quote(path)}',
                          params={'ref': branch})
            return True
        except UserError:
            return False

    def _free_name(self, repo, branch, subdir, filename):
        stem, dot, ext = filename.rpartition('.')
        candidate, counter = filename, 0
        while True:
            path = f'{subdir}/{candidate}' if subdir else candidate
            if not self._exists(repo, branch, path):
                return candidate
            counter += 1
            candidate = (f'{stem} ({counter}).{ext}'
                         if dot else f'{filename} ({counter})')

    def create_shared_link(self, file, expires=None):
        """The blob's page on GitHub. It only opens for people who can
        see the repository -- this share does not pierce the gate, and
        it has no expiry to speak of (expires is ignored by design)."""
        repo = self._repo(file.folder_id)
        branch = self._branch(file.folder_id)
        return 'https://github.com/%s/blob/%s/%s' % (
            repo, quote(branch), quote(self._file_repo_path(file)))

    def get_thumbnail_batch(self, files):
        # Downloading every image just to shrink it is not worth the
        # bandwidth for a code host; file cards it is.
        return {}
