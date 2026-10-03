# -*- coding: utf-8 -*-
from odoo.exceptions import UserError


class CloudFileGone(UserError):
    """The storage answered that the file is not there any more.

    Deleted, renamed or moved upstream after the last sync: the mirror
    still points at the old path. `detail` carries what the provider
    knows about how it went (on GitHub, the last commit on that path),
    or '' when it knows nothing more.
    """

    def __init__(self, message, detail=''):
        super().__init__(message)
        self.detail = detail
