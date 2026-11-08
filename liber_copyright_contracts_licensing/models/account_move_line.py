# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    edlab_license_work_id = fields.Many2one(
        "product.template",
        string="Licensed Work",
        index=True,
        copy=True,
        help="Work of the contract this licensing line licenses. Its "
        "beneficiaries' analytic accounts go on the line. Empty on a "
        "single-work contract means that work.",
    )

    # ------------------------------------------------------------------
    # Defaults of a licensing line, computed on the SERVER
    # ------------------------------------------------------------------
    # Not set by the form's onchange: the analytic column is only on screen
    # for users with analytic accounting, and a value the form does not show
    # is a value it does not send back -- a licence saved by anyone else lost
    # the author's account, silently. Account and analytic are computed
    # fields already; these overrides only add the licensing rule to them,
    # so they hold whoever saves and stay editable afterwards.
    def _edlab_license_work(self):
        """The work this line licenses (explicit, else the contract's only
        one); empty when the line is not a licensing line."""
        self.ensure_one()
        contract = self.move_id.edlab_license_contract_id
        if not contract or self.display_type != "product":
            return self.env["product.template"]
        if self.edlab_license_work_id:
            return self.edlab_license_work_id
        works = contract.royalty_line_ids.product_id
        return works if len(works) == 1 else self.env["product.template"]

    @api.depends("edlab_license_work_id", "move_id.edlab_license_contract_id")
    def _compute_name(self):
        """The line says WHAT was licensed: "Licensing of <title> (contract
        <number>)". Core names a line after its product, and the product is
        the generic licensing service -- the licensee's invoice would read
        "Rights licensing" and nothing else. Only a product-derived (or
        empty) name is replaced: a description the user typed stays."""
        super()._compute_name()
        for line in self:
            work = line._edlab_license_work()
            if not work:
                continue
            product_name = line.product_id.display_name or ""
            if line.name and not (product_name and line.name.startswith(product_name)):
                continue
            line.name = _("Licensing of %(work)s (contract %(contract)s)",
                          work=work.display_name,
                          contract=line.move_id.edlab_license_contract_id.name)

    def _compute_account_id(self):
        super()._compute_account_id()
        for line in self:
            move = line.move_id
            if not move.edlab_license_contract_id or line.display_type != "product":
                continue
            company = move.edlab_license_contract_id.company_id
            account = company.contract_license_account_id
            if account and line.product_id == company._contract_license_product():
                line.account_id = account

    @api.depends("edlab_license_work_id", "move_id.edlab_license_contract_id")
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        for line in self:
            work = line._edlab_license_work()
            if not work:
                continue
            royalties = line.move_id.edlab_license_contract_id.royalty_line_ids.filtered(
                lambda r: r.product_id == work and r.analytic_account_id)
            if not royalties:
                continue
            # Each beneficiary at 100%: they all take their licensing % of
            # the WHOLE amount (see edlab.contract._edlab_license_line_commands).
            line.analytic_distribution = dict(
                line.analytic_distribution or {},
                **{str(account.id): 100.0
                   for account in royalties.analytic_account_id})

    def _prepare_analytic_lines(self):
        """Keep the licensing revenue off the author's analytic account.

        On a licensing invoice the beneficiary's analytic account sits on the
        line to SAY whose rights were licensed -- and core would answer by
        posting the full invoiced amount (+100%) on it. That account holds
        what the house owes the author (accruals negative, settlements
        positive); a R$ 1.000 licence showing up there as +1.000 would make
        the plan balance of the account (its form, the plan reports) claim
        the author owes the house. What belongs there is the author's share,
        booked by the licensing sync when the invoice is paid.

        Only the contract's royalty accounts are dropped: any other plan on
        the same line (a project, a cost centre) keeps its entry."""
        vals_list = super()._prepare_analytic_lines()
        contract = self.move_id.edlab_license_contract_id
        if not contract or not vals_list:
            return vals_list
        royalty_accounts = set(contract.sudo().royalty_line_ids.analytic_account_id.ids)
        if not royalty_accounts:
            return vals_list
        columns = {
            plan._column_name()
            for plan in self.env["account.analytic.plan"].sudo().search([])
        }
        kept = []
        for vals in vals_list:
            remaining = {
                col: vals[col] for col in columns
                if vals.get(col) and vals[col] not in royalty_accounts
            }
            if not remaining:
                continue
            for col in columns:
                if vals.get(col) in royalty_accounts:
                    vals[col] = False
            kept.append(vals)
        return kept
