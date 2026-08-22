# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _remessa_account_for_fiscal_position(self, fiscal_position):
        """The account a remessa under this fiscal position books to.

        Not invented here: it is read from the account map the accountant
        already filled on the fiscal position -- "revenue account X becomes
        account Y for this operation". Consignment sends it to the consignment
        investment account, a bonus to its own, and the map is where that was
        declared long before this code existed.

        Only the mapping that starts on a REVENUE account counts. A remessa
        line is, structurally, the revenue line of an out_invoice: it is that
        account, and no other, that the operation redirects.
        """
        self.ensure_one()
        income = fiscal_position.account_ids.filtered(
            lambda m: m.account_src_id.account_type == 'income')
        if len(income) != 1:
            raise UserError(_(
                "Fiscal position %(fpos)s does not say where a remessa books: "
                "it needs exactly one account mapping starting on a revenue "
                "account (found %(n)s). Fill it in Accounting > Fiscal "
                "Positions -- a remessa is not revenue, and the map is what "
                "moves it out of revenue.",
                fpos=fiscal_position.display_name or _("(none)"),
                n=len(income)))
        return income.account_dest_id

    def _get_remessa_journal(self, kind='other', fiscal_position=None,
                             name=None, code=None):
        """The company's remessa journal for one kind, created on first use.

        Mirrors how consignment operation types come to exist: nobody
        configures them, the first document needs one and it appears. What is
        NOT invented is the account: the journal is born carrying the account
        its operation's fiscal position declares, so the line has an account
        even for the house catalogue, where no product and no category has one
        and the journal is the only remaining source.

        There is one journal per kind (REM-C, REM-B, ...) and not one shared
        REM: the account of last resort lives on the journal, and each
        operation books to a different one. The fiscal numbering is untouched
        -- número and série of the NF-e come from the company, not from this
        sequence.
        """
        self.ensure_one()
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.id),
            ('is_remessa', '=', True),
            ('remessa_kind', '=', kind),
        ], limit=1)
        if journal:
            return journal
        vals = {
            'name': name or _("Remessas"),
            'code': code or 'REM',
            'type': 'sale',
            'is_remessa': True,
            'remessa_kind': kind,
            'company_id': self.id,
        }
        if fiscal_position:
            vals['default_account_id'] = \
                self._remessa_account_for_fiscal_position(fiscal_position).id
        return self.env['account.journal'].sudo().create(vals)

    def _remessa_journals_out_of_sync(self):
        """Remessa journals whose account no longer matches the fiscal position.

        The journal carries a photograph of the map taken the day it was born.
        Change the map afterwards and the journal keeps booking to the old
        account -- silently, which is the worst way to be wrong about money.
        This is what the test (and anyone in doubt) asks; it returns a list of
        (journal, expected account) for every disagreement.

        Each module that owns a kind declares the fiscal position that rules
        it in `_remessa_fiscal_position_by_kind`.
        """
        divergentes = []
        for company in self:
            por_kind = company._remessa_fiscal_position_by_kind()
            for kind, fpos in por_kind.items():
                if not fpos:
                    continue
                journal = self.env['account.journal'].search([
                    ('company_id', '=', company.id),
                    ('is_remessa', '=', True),
                    ('remessa_kind', '=', kind),
                ], limit=1)
                if not journal:
                    continue
                esperada = company._remessa_account_for_fiscal_position(fpos)
                if journal.default_account_id != esperada:
                    divergentes.append((journal, esperada))
        return divergentes

    def _remessa_fiscal_position_by_kind(self):
        """{kind: fiscal position} -- each module adds its own kind."""
        self.ensure_one()
        return {}
