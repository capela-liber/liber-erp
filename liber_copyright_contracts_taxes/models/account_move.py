# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
import calendar

from odoo import _, api, fields, models
from odoo.tools import float_round


class AccountMove(models.Model):
    _inherit = "account.move"

    edlab_is_tax_bill = fields.Boolean(
        string="IRRF Tax Bill",
        copy=False,
        help="Accumulator vendor bill that gathers the IRRF withheld from the "
        "author payment bills (one line per work).",
    )
    edlab_tax_move_id = fields.Many2one(
        "account.move",
        string="IRRF Tax Bill",
        index=True,
        ondelete="set null",
        copy=False,
        help="Tax bill (batch) carrying the IRRF withheld from this author "
        "payment bill.",
    )
    edlab_tax_origin_bill_ids = fields.One2many(
        "account.move",
        "edlab_tax_move_id",
        string="Withheld From",
    )
    edlab_tax_origin_count = fields.Integer(
        compute="_compute_edlab_tax_origin_count",
        string="Author Bills",
    )

    @api.depends("edlab_tax_origin_bill_ids")
    def _compute_edlab_tax_origin_count(self):
        for move in self:
            move.edlab_tax_origin_count = len(move.edlab_tax_origin_bill_ids)

    # ------------------------------------------------------------------
    # Hooks: keep the accumulator tax bill in sync with the author bills
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            if (
                move.move_type == "in_invoice"
                and not move.edlab_is_tax_bill
                and any(l.edlab_irrf_withholding for l in move.invoice_line_ids)
            ):
                move._edlab_sync_tax_bill()
        return moves

    def action_post(self):
        res = super().action_post()
        for move in self:
            if move.edlab_is_tax_bill or move.move_type != "in_invoice":
                continue
            if any(l.edlab_irrf_withholding for l in move.invoice_line_ids):
                if move.edlab_tax_move_id:
                    # The bill now has its real number: refresh the tax bill
                    # line labels and the Payment Reference.
                    move._edlab_sync_tax_bill()
                else:
                    # Re-posting after a cancel that removed the tax lines.
                    move._edlab_sync_tax_bill()
        return res

    def button_cancel(self):
        res = super().button_cancel()
        self.filtered(
            lambda m: m.move_type == "in_invoice" and m.edlab_tax_move_id
        )._edlab_remove_from_tax_bill()
        return res

    def unlink(self):
        self.filtered(
            lambda m: m.move_type == "in_invoice" and m.edlab_tax_move_id
        )._edlab_remove_from_tax_bill()
        return super().unlink()

    # ------------------------------------------------------------------
    # Tax bill accumulation
    # ------------------------------------------------------------------
    def _edlab_bill_display(self):
        """Human reference of an author bill: its number once posted, the
        'contract - beneficiary' ref while still a draft."""
        self.ensure_one()
        if self.name and self.name != "/":
            return self.name
        return self.ref or self.partner_id.display_name or _("draft")

    def _edlab_get_draft_tax_bill(self, company):
        """The company's current accumulator (a draft tax bill), if any."""
        return self.sudo().search(
            [
                ("edlab_is_tax_bill", "=", True),
                ("move_type", "=", "in_invoice"),
                ("company_id", "=", company.id),
                ("state", "=", "draft"),
            ],
            order="id",
            limit=1,
        )

    def _edlab_create_tax_bill(self, company):
        """New accumulator: next batch number, due on the configured day of
        the following month."""
        today = fields.Date.context_today(self)
        due_day = company.contract_tax_due_day or 20
        nxt = today + relativedelta(months=1)
        due = nxt.replace(day=min(due_day, calendar.monthrange(nxt.year, nxt.month)[1]))
        vals = {
            "move_type": "in_invoice",
            "partner_id": company.contract_tax_partner_id.id,
            "invoice_date": today,
            "invoice_date_due": due,
            "company_id": company.id,
            "edlab_is_tax_bill": True,
            "ref": self.env["ir.sequence"].sudo().next_by_code(
                "edlab.irrf.tax.batch"
            ),
        }
        if company.contract_tax_journal_id:
            vals["journal_id"] = company.contract_tax_journal_id.id
        return self.sudo().with_company(company).create(vals)

    def _edlab_sync_tax_bill(self):
        """Create/update the tax bill lines for this author bill.

        One line per work line of the author bill, splitting the withheld
        IRRF proportionally to each work's amount (last line absorbs the
        rounding remainder). Replaces this bill's previous lines on the draft
        accumulator, so re-generation never duplicates.
        """
        self.ensure_one()
        company = self.company_id
        if not (company.contract_tax_partner_id and company.contract_tax_account_id):
            return
        irrf = -sum(
            self.invoice_line_ids.filtered("edlab_irrf_withholding").mapped(
                "price_subtotal"
            )
        )
        if float_round(irrf, precision_digits=2) <= 0:
            return
        tax_bill = self.edlab_tax_move_id
        if not tax_bill or tax_bill.state != "draft":
            tax_bill = self._edlab_get_draft_tax_bill(company)
        if not tax_bill:
            tax_bill = self._edlab_create_tax_bill(company)
        book_lines = self.invoice_line_ids.filtered("edlab_royalty_line_id")
        gross = sum(book_lines.mapped("price_subtotal")) or 1.0
        commands = [
            (2, line.id)
            for line in tax_bill.invoice_line_ids.filtered(
                lambda l: l.edlab_tax_source_move_id == self
            )
        ]
        remaining = irrf
        for index, line in enumerate(book_lines):
            if index < len(book_lines) - 1:
                part = float_round(
                    irrf * line.price_subtotal / gross, precision_digits=2
                )
            else:
                part = float_round(remaining, precision_digits=2)
            remaining -= part
            royalty = line.edlab_royalty_line_id
            commands.append(
                (0, 0, {
                    "name": _("IRRF - %s - %s")
                    % (royalty.product_id.display_name, self._edlab_bill_display()),
                    "quantity": 1.0,
                    "price_unit": part,
                    "account_id": company.contract_tax_account_id.id,
                    "tax_ids": [(6, 0, [])],
                    "edlab_tax_source_move_id": self.id,
                    "edlab_tax_royalty_line_id": royalty.id,
                })
            )
        tax_bill.sudo().write({"invoice_line_ids": commands})
        if self.edlab_tax_move_id != tax_bill:
            self.edlab_tax_move_id = tax_bill
        tax_bill._edlab_tax_refresh_refs()

    def _edlab_remove_from_tax_bill(self):
        """Drop this author bill's lines from its (draft) tax bill; a posted
        batch is never touched - just flagged for the accountant."""
        for move in self:
            tax_bill = move.edlab_tax_move_id
            if not tax_bill:
                continue
            if tax_bill.state == "draft":
                commands = [
                    (2, line.id)
                    for line in tax_bill.invoice_line_ids.filtered(
                        lambda l: l.edlab_tax_source_move_id == move
                    )
                ]
                if commands:
                    tax_bill.sudo().write({"invoice_line_ids": commands})
                tax_bill._edlab_tax_refresh_refs()
            else:
                tax_bill.message_post(
                    body=_(
                        "Author bill %s was cancelled or deleted after this "
                        "tax batch was posted - manual adjustment needed.",
                        move._edlab_bill_display(),
                    )
                )
            move.edlab_tax_move_id = False

    def _edlab_tax_refresh_refs(self):
        """Payment Reference of the tax bill = the contracts and the author
        bills its lines came from (recomputed from the M2O links, so it stays
        correct whatever the state of each bill)."""
        for tax_bill in self:
            lines = tax_bill.invoice_line_ids.filtered("edlab_tax_source_move_id")
            contracts = list(dict.fromkeys(
                lines.mapped("edlab_tax_royalty_line_id.contract_id.name")
            ))
            bills = list(dict.fromkeys(
                source._edlab_bill_display()
                for source in lines.mapped("edlab_tax_source_move_id")
            ))
            parts = []
            if contracts:
                parts.append(_("Contracts: %s") % ", ".join(contracts))
            if bills:
                parts.append(_("Bills: %s") % ", ".join(bills))
            tax_bill.payment_reference = " | ".join(parts)

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------
    def action_open_tax_bill(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.edlab_tax_move_id.id,
            "view_mode": "form",
        }

    def action_open_tax_origin_bills(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Author Bills"),
            "res_model": "account.move",
            "domain": [("edlab_tax_move_id", "=", self.id)],
            "view_mode": "list,form",
            "context": {"create": False, "default_move_type": "in_invoice"},
        }
