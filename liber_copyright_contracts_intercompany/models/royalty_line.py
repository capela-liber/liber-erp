# -*- coding: utf-8 -*-
from odoo import models


class EdlabContractRoyaltyLine(models.Model):
    _inherit = "edlab.contract.royalty.line"

    def _book_royalties_from_invoices(self, invoices):
        res = super()._book_royalties_from_invoices(invoices)
        # Runs on every booking, including the payments module's empty-recordset
        # call on bill payment: the sync is a full recompute, so re-running is
        # free and keeps the accumulator honest after any accrual change.
        self._edlab_sync_interco_charge()
        return res

    def _edlab_sync_interco_charge(self):
        """Accumulate the cross-company accruals of these royalty lines on
        the intercompany royalty invoice (contract company -> selling
        company), one draft accumulator per (contract company, source
        company) pair."""
        Move = self.env["account.move"]
        AnalyticLine = self.env["account.analytic.line"].sudo()
        lines = self.filtered("analytic_account_id")
        for company in lines.company_id:
            # Charging is optional and must NEVER block the accrual: without
            # a product (deleted and not reconfigured) just skip the charge.
            if not company._contract_interco_product():
                continue
            company_lines = lines.filtered(lambda r: r.company_id == company)
            accruals = AnalyticLine.search([
                ("account_id", "in", company_lines.analytic_account_id.ids),
                ("edlab_source_company_id", "!=", False),
                ("edlab_source_company_id", "!=", company.id),
            ])
            # Frozen accruals (charged on a POSTED pair) are settled history;
            # only free ones and ones on a draft pair drive the sync.
            accruals = accruals.filtered(
                lambda a: not a.edlab_interco_move_line_id
                or a.edlab_interco_move_line_id.move_id.state == "draft")
            for source in accruals.edlab_source_company_id:
                invoice = (
                    Move._edlab_get_draft_interco_invoice(company, source)
                    or Move._edlab_create_interco_invoice(company, source)
                )
                invoice._edlab_sync_interco_lines(company_lines)
