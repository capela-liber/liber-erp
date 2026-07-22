# -*- coding: utf-8 -*-
"""The contract every storage client honours.

A provider module contributes one client class and registers it on the
``liber.cloud.provider`` abstract model (see models/cloud_provider.py).
The base never imports a provider; it only calls this interface:

    check()
        Return a dict describing the authenticated account
        (``{'name': ..., 'email': ...}``-ish); raise UserError otherwise.

    list_folder(folder, exclude=<folders>)
        Return a list of file entries under the mapped folder --
        recursively when ``folder.recursive`` -- skipping every subtree
        that belongs to a folder in ``exclude`` (they are mapped on their
        own; their ACL rules there). Each entry is a dict:
        ``{'name', 'path', 'external_id', 'size', 'rev',
           'content_hash', 'client_modified'}``
        where ``path`` is the stable display path used as the mirror key
        and ``client_modified`` is a naive-UTC datetime or False.

    temporary_link(file)
        A short-lived direct URL the browser can open, or None when the
        provider has no such thing -- the base then streams the download
        through Odoo (see controllers/main.py).

    download(file)
        The file's bytes, fetched with the account credential. Only
        called when temporary_link() returned None.

    upload(folder, filename, data)
        Put bytes into the mapped folder, never silently overwriting
        (rename on conflict is the convention).

    create_shared_link(file, expires=None)
        Create (or refresh) the provider's shared link and return its
        URL. ``expires`` is a naive-UTC datetime or None; providers that
        cannot expire links raise a clear UserError or ignore it --
        each documents which.

    get_thumbnail_batch(files)
        ``{path: base64-image}`` for the files the provider can render;
        silently absent entries mean "no thumbnail", never an error.

Helpers shared by providers live here too.
"""

# The image formats worth asking a thumbnail for; PDFs and the rest get a
# plain file card and open full-size in the browser instead.
THUMBNAIL_EXTENSIONS = (
    'jpg', 'jpeg', 'png', 'tif', 'tiff', 'gif', 'webp', 'ppm', 'bmp')


def wants_thumbnail(name):
    return ('.' in name
            and name.rsplit('.', 1)[-1].lower() in THUMBNAIL_EXTENSIONS)
