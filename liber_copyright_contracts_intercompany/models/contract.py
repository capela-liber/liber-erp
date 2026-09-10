# -*- coding: utf-8 -*-
from odoo import models


class EdlabContract(models.Model):
    _inherit = "edlab.contract"

    def _edlab_royalty_invoice_domain(self):
        """Accrue on the contract company's own sales plus the configured
        source companies' -- and nothing else. This replaces the old
        behaviour of silently sweeping every company's invoices."""
        domain = super()._edlab_royalty_invoice_domain()
        # sudo: the multi-company record rule on res.company would silently
        # DROP source companies the user cannot see, shrinking the accrual to
        # own sales only for anyone without access to the selling companies.
        company = (self.company_id or self.env.company).sudo()
        allowed = company | company.contract_interco_source_company_ids
        return domain + [("company_id", "in", allowed.ids)]
