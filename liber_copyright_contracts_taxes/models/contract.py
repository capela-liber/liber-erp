# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.tools import float_round


class EdlabContract(models.Model):
    _inherit = "edlab.contract"

    def _prepare_royalty_bill_vals(self, partner, items, company):
        """Withhold the IRRF on the author's bill as a negative line.

        Opt-in: only when the company's tax settings (authority + liability
        account) are configured. The line hits the 'IRRF to pay' liability
        account, so the bill books gross expense / net payable / IRRF
        liability - the government tax bill later clears that liability.
        """
        vals = super()._prepare_royalty_bill_vals(partner, items, company)
        if not (company.contract_tax_partner_id and company.contract_tax_account_id):
            return vals
        gross = sum(owed for _line, owed in items)
        irrf = self.env["edlab.irrf.table"]._irrf_for_partner(
            partner, gross, vals.get("invoice_date")
        )
        if float_round(irrf, precision_digits=2) <= 0:
            return vals
        vals["invoice_line_ids"].append(
            (0, 0, {
                "name": _("IRRF withheld - %s") % partner.name,
                "quantity": 1.0,
                "price_unit": -irrf,
                "account_id": company.contract_tax_account_id.id,
                "tax_ids": [(6, 0, [])],
                "edlab_irrf_withholding": True,
            })
        )
        return vals
