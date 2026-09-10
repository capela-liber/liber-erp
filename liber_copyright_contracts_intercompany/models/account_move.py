# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.tools import float_compare, float_round


class AccountMove(models.Model):
    _inherit = "account.move"

    edlab_is_interco_invoice = fields.Boolean(
        string="Intercompany Royalty Invoice",
        copy=False,
        help="Accumulator customer invoice of the contract company charging "
        "a selling company for the royalties accrued on its sales (one line "
        "per contract x work x beneficiary).",
    )
    edlab_is_interco_bill = fields.Boolean(
        string="Intercompany Royalty Bill",
        copy=False,
        help="Vendor bill of the selling company mirroring the posted "
        "intercompany royalty invoice of the contract company.",
    )
    edlab_interco_source_company_id = fields.Many2one(
        "res.company",
        string="Charged Company",
        copy=False,
        help="Selling company this intercompany royalty invoice charges.",
    )
    edlab_interco_mirror_move_id = fields.Many2one(
        "account.move",
        string="Origin Intercompany Invoice",
        index=True,
        ondelete="set null",
        copy=False,
        help="Customer invoice (on the contract company) this vendor bill "
        "mirrors.",
    )
    edlab_interco_mirror_of_ids = fields.One2many(
        "account.move",
        "edlab_interco_mirror_move_id",
        string="Mirror Bills",
    )
    edlab_interco_mirror_count = fields.Integer(
        compute="_compute_edlab_interco_mirror_count",
        string="Mirror Bills Count",
    )

    @api.depends("edlab_interco_mirror_of_ids")
    def _compute_edlab_interco_mirror_count(self):
        for move in self:
            move.edlab_interco_mirror_count = len(
                move.edlab_interco_mirror_of_ids)

    # ------------------------------------------------------------------
    # Accumulator invoice (contract company side)
    # ------------------------------------------------------------------
    @api.model
    def _edlab_get_draft_interco_invoice(self, company, source):
        """The company's current accumulator charging `source`, if any."""
        return self.sudo().search(
            [
                ("edlab_is_interco_invoice", "=", True),
                ("move_type", "=", "out_invoice"),
                ("company_id", "=", company.id),
                ("edlab_interco_source_company_id", "=", source.id),
                ("state", "=", "draft"),
            ],
            order="id",
            limit=1,
        )

    @api.model
    def _edlab_create_interco_invoice(self, company, source):
        """New accumulator: contract company invoices the selling company."""
        vals = {
            "move_type": "out_invoice",
            "partner_id": source.partner_id.id,
            "invoice_date": fields.Date.context_today(self),
            "company_id": company.id,
            "edlab_is_interco_invoice": True,
            "edlab_interco_source_company_id": source.id,
            "ref": self.env["ir.sequence"].sudo().next_by_code(
                "edlab.interco.royalty.batch"),
        }
        # Only a SALE journal: Odoo refuses a sale document in any other kind
        # ("Cannot create a sale document in a non sale journal"), and that
        # ValidationError would abort the whole royalty fill over a setting
        # that is merely a preference. Wrong type = fall back to the default.
        # sudo: the type check READS the journal, and the journal belongs to
        # another company than the user's active one often enough (posting
        # with only the holder active) -- the multi-company rule would turn
        # the guard itself into an AccessError.
        journal = company.sudo().contract_interco_journal_id
        if journal.type == "sale":
            vals["journal_id"] = journal.id
        return self.sudo().with_company(company).create(vals)

    def _edlab_sync_interco_lines(self, royalty_lines):
        """Recompute this draft accumulator's lines for `royalty_lines`.

        Full recompute, never incremental (the IRRF tax bill pattern): each
        line's value is the CURRENT total of the royalty line's accruals
        sourced from the charged company that are not frozen on a posted
        pair. Reversed or deleted accruals shrink the line for free, and
        re-running never duplicates. Royalty lines already on the invoice
        are recomputed too, so a line whose accruals vanished is dropped.
        """
        self.ensure_one()
        company = self.company_id
        source = self.edlab_interco_source_company_id
        product = company._contract_interco_product()
        markup = 1 + (company.contract_interco_markup or 0.0) / 100.0
        AnalyticLine = self.env["account.analytic.line"].sudo()
        targets = (
            royalty_lines
            | self.invoice_line_ids.edlab_interco_royalty_line_id
        )
        commands = [
            (2, line.id)
            for line in self.invoice_line_ids.filtered(
                lambda l: l.edlab_interco_royalty_line_id in targets)
        ]
        charged = []
        for royalty in targets.filtered("analytic_account_id"):
            accruals = AnalyticLine.search([
                ("account_id", "=", royalty.analytic_account_id.id),
                ("edlab_source_company_id", "=", source.id),
                "|",
                ("edlab_interco_move_line_id", "=", False),
                ("edlab_interco_move_line_id.move_id", "=", self.id),
            ])
            # Accrual amounts are negative (royalty owed), so the charge is
            # their negated sum.
            total = float_round(
                -sum(accruals.mapped("amount")) * markup, precision_digits=2)
            if not accruals or float_compare(
                    total, 0.0, precision_digits=2) <= 0:
                accruals.write({"edlab_interco_move_line_id": False})
                continue
            vals = {
                "name": "%s - %s - %s - %s" % (
                    product.display_name,
                    royalty.contract_id.name,
                    royalty.product_id.display_name,
                    royalty.partner_id.name,
                ),
                "product_id": product.id,
                "quantity": 1.0,
                "price_unit": total,
                "edlab_interco_royalty_line_id": royalty.id,
            }
            if company.contract_interco_income_account_id:
                vals["account_id"] = company.contract_interco_income_account_id.id
            commands.append((0, 0, vals))
            charged.append((royalty, accruals))
        self.sudo().write({"invoice_line_ids": commands})
        for royalty, accruals in charged:
            new_line = self.invoice_line_ids.filtered(
                lambda l: l.edlab_interco_royalty_line_id == royalty)[:1]
            accruals.write({"edlab_interco_move_line_id": new_line.id})
        self._edlab_interco_refresh_refs()

    def _edlab_interco_refresh_refs(self):
        """Payment Reference = the contracts the charge came from."""
        for invoice in self:
            contracts = list(dict.fromkeys(
                invoice.invoice_line_ids
                .edlab_interco_royalty_line_id.contract_id.mapped("name")))
            invoice.payment_reference = (
                _("Contracts: %s") % ", ".join(contracts)
                if contracts else False)

    # ------------------------------------------------------------------
    # Mirror bill (selling company side): born only when the invoice is
    # posted. While accumulating there is exactly ONE live document, which
    # removes the whole class of two-drafts-diverging bugs.
    # ------------------------------------------------------------------
    def action_post(self):
        res = super().action_post()
        for move in self.filtered(
                lambda m: m.edlab_is_interco_invoice
                and m.move_type == "out_invoice"):
            if not move.edlab_interco_mirror_of_ids.filtered(
                    lambda b: b.state != "cancel"):
                move._edlab_create_mirror_bill()
        return res

    def _edlab_create_mirror_bill(self):
        self.ensure_one()
        source = self.edlab_interco_source_company_id
        expense = source.contract_interco_expense_account_id
        line_cmds = []
        for line in self.invoice_line_ids.filtered(
                "edlab_interco_royalty_line_id"):
            vals = {
                "product_id": line.product_id.id,
                "name": line.name,
                "quantity": line.quantity,
                "price_unit": line.price_unit,
                "edlab_interco_royalty_line_id":
                    line.edlab_interco_royalty_line_id.id,
            }
            if expense:
                vals["account_id"] = expense.id
            line_cmds.append((0, 0, vals))
        vals = {
            "move_type": "in_invoice",
            "partner_id": self.company_id.partner_id.id,
            "company_id": source.id,
            "invoice_date": self.invoice_date or fields.Date.context_today(self),
            "ref": self.name,
            "edlab_is_interco_bill": True,
            "edlab_interco_mirror_move_id": self.id,
            "invoice_line_ids": line_cmds,
        }
        # Same guard as the invoice side, mirrored: a non-purchase journal
        # would raise and leave the posted invoice without its counterpart.
        # sudo: the selling company's journal is exactly the record the
        # poster's multi-company rule cannot read when only the holder
        # company is active -- the type check must not be the crash.
        journal = source.sudo().contract_interco_purchase_journal_id
        if journal.type == "purchase":
            vals["journal_id"] = journal.id
        return self.sudo().with_company(source).create(vals)

    # ------------------------------------------------------------------
    # Coexistence with account_invoice_inter_company (OCA). That module
    # mirrors any invoice whose partner is a sister company, deciding through
    # _find_company_from_invoice_partner(). Royalty documents are already born
    # as a pair (the invoice creates its own mirror bill above), so with both
    # modules installed every royalty invoice would get a second bill, and the
    # bill a second invoice. Answer "no sister company" for them. Works with or
    # without the OCA module: without it there is no super() to call.
    # ------------------------------------------------------------------
    def _find_company_from_invoice_partner(self):
        self.ensure_one()
        if self.edlab_is_interco_invoice or self.edlab_is_interco_bill:
            return False
        parent = getattr(super(), "_find_company_from_invoice_partner", None)
        return parent() if parent else False

    def button_draft(self):
        res = super().button_draft()
        # Back to draft = back to accumulating. A draft mirror would then
        # diverge line by line, so drop it; a posted mirror is the selling
        # company's to reverse -- flag it in its chatter instead.
        for move in self.filtered("edlab_is_interco_invoice"):
            mirrors = move.edlab_interco_mirror_of_ids
            drafts = mirrors.filtered(lambda b: b.state == "draft")
            for bill in mirrors.filtered(lambda b: b.state == "posted"):
                bill.sudo().message_post(body=_(
                    "Origin intercompany invoice %s was reset to draft after "
                    "this bill was posted - manual adjustment needed.",
                    move.name))
            drafts.sudo().unlink()
        return res

    def button_cancel(self):
        res = super().button_cancel()
        # Cancelled charge = accruals free again: the next fill rebuilds the
        # pair from scratch.
        self.filtered(
            "edlab_is_interco_invoice")._edlab_release_interco_accruals()
        return res

    def unlink(self):
        self.filtered(
            "edlab_is_interco_invoice")._edlab_release_interco_accruals()
        return super().unlink()

    def _edlab_release_interco_accruals(self):
        self.env["account.analytic.line"].sudo().search([
            ("edlab_interco_move_line_id.move_id", "in", self.ids),
        ]).write({"edlab_interco_move_line_id": False})

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------
    def action_open_interco_mirror_bills(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Mirror Bills"),
            "res_model": "account.move",
            "domain": [("edlab_interco_mirror_move_id", "=", self.id)],
            "view_mode": "list,form",
            "context": {"create": False, "default_move_type": "in_invoice"},
        }

    def action_open_interco_origin_invoice(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.edlab_interco_mirror_move_id.id,
            "view_mode": "form",
        }
