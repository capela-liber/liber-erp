# -*- coding: utf-8 -*-
from odoo import _, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _get_remessa_journal(self):
        """The company's remessa journal, created on first use.

        Mirrors how consignment operation types come to exist: nobody
        configures them, the first document needs one and it appears. Code
        REM -- the fiscal document owns the prefix; consignment logistics
        moved to COM/.
        """
        self.ensure_one()
        journal = self.env['account.journal'].search(
            [('company_id', '=', self.id), ('is_remessa', '=', True)], limit=1)
        if not journal:
            journal = self.env['account.journal'].sudo().create({
                'name': _("Remessas"),
                'code': 'REM',
                'type': 'sale',
                'is_remessa': True,
                'company_id': self.id,
            })
        return journal
