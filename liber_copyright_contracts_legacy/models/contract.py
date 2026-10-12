# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class EdlabContract(models.Model):
    _inherit = "edlab.contract"

    legacy_enabled = fields.Boolean(
        string="Legacy sales",
        tracking=True,
        help="Accrue royalties on the sales of the contracted works made "
        "before this system (the imported legacy base), and count those "
        "copies in the cumulative quantity that selects the royalty tier.")
    legacy_index_id = fields.Many2one(
        "edlab.price.index", string="Price index",
        tracking=True,
        help="Corrects each month of legacy sales to the reference month "
        "before applying the percentage. Empty = nominal values, in the "
        "money of the time.")
    legacy_reference_date = fields.Date(
        string="Reference month",
        help="Month the legacy amounts are corrected TO. Empty = the last "
        "month published in the index.")
    legacy_date_from = fields.Date(
        string="Legacy from",
        help="Ignore legacy sales before this date (e.g. a period already "
        "settled under a previous contract). Empty = from the beginning.")
    legacy_date_to = fields.Date(
        string="Legacy until",
        help="Ignore legacy sales after this date. Empty = the whole base.")

    legacy_sale_count = fields.Integer(compute="_compute_legacy_stats")
    legacy_qty = fields.Float(
        string="Legacy copies", compute="_compute_legacy_stats",
        digits=(16, 2),
        help="Copies sold (returns deducted) in the legacy base, for the "
        "contracted works and within the legacy window.")
    legacy_base = fields.Monetary(
        string="Legacy base (nominal)", compute="_compute_legacy_stats",
        currency_field="currency_id")
    legacy_accrued = fields.Monetary(
        string="Legacy royalties booked", compute="_compute_legacy_stats",
        currency_field="currency_id",
        help="Royalties already booked on the analytic accounts from the "
        "legacy base (corrected, when an index is set).")

    @api.depends("legacy_enabled", "legacy_date_from", "legacy_date_to",
                 "royalty_line_ids.product_id", "royalty_line_ids.tier_ids")
    def _compute_legacy_stats(self):
        Sale = self.env["edlab.legacy.sale"].sudo()
        for contract in self:
            templates = contract.royalty_line_ids.product_id
            domain = [("product_tmpl_id", "in", templates.ids), ("counts", "=", True)]
            if contract.legacy_date_from:
                domain.append(("date", ">=", contract.legacy_date_from))
            if contract.legacy_date_to:
                domain.append(("date", "<=", contract.legacy_date_to))
            contract.legacy_sale_count = Sale.search_count(
                [("product_tmpl_id", "in", templates.ids)]) if templates else 0
            qty = base = 0.0
            if templates and contract.legacy_enabled:
                groups = Sale._read_group(
                    domain, [], ["signed_quantity:sum", "royalty_base:sum"])
                if groups:
                    qty, base = groups[0]
            contract.legacy_qty = qty or 0.0
            contract.legacy_base = base or 0.0
            contract.legacy_accrued = sum(
                line._edlab_legacy_accrued()
                for line in contract.royalty_line_ids
                if line.analytic_account_id) if contract.legacy_enabled else 0.0

    @api.constrains("legacy_enabled", "legacy_index_id", "legacy_reference_date")
    def _check_legacy_reference(self):
        for contract in self:
            if contract.legacy_reference_date and not contract.legacy_index_id:
                raise ValidationError(_(
                    "A reference month only makes sense with a price index."))

    def _edlab_legacy_reference_date(self):
        """Month the legacy amounts are corrected to: the one chosen on the
        contract, else the last month the index has."""
        self.ensure_one()
        index = self.legacy_index_id
        if not index:
            return False
        if self.legacy_reference_date:
            return self.legacy_reference_date
        if not index.last_date:
            raise UserError(_(
                "The index %s has no monthly values yet. Refresh it from the "
                "Central Bank or type the months in.", index.display_name))
        return index.last_date

    def action_fill_royalty_lines(self):
        """Legacy first, so the payment cutoff computed by the engine already
        sees the legacy accruals when it settles what was paid."""
        self.filtered("legacy_enabled").royalty_line_ids.filtered(
            "analytic_account_id")._edlab_book_legacy()
        return super().action_fill_royalty_lines()

    def action_book_legacy(self):
        lines = self.royalty_line_ids.filtered("analytic_account_id")
        if not self.filtered("legacy_enabled"):
            raise UserError(_("Switch 'Legacy sales' on first."))
        if not lines:
            raise UserError(_(
                "No royalty line has an analytic account yet. Create the "
                "analytic accounts first."))
        created, updated, removed = lines._edlab_book_legacy()
        no_tier = lines.filtered(lambda l: not l.tier_ids)
        message = _("%(c)s month(s) booked, %(u)s refreshed, %(r)s removed.",
                    c=created, u=updated, r=removed)
        if no_tier:
            message += _(" %s royalty line(s) have no tier and were skipped.",
                         len(no_tier))
        if not (created or updated or removed):
            message = _("Nothing to change: the legacy accruals already "
                        "mirror the base.")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Legacy sales"), "message": message,
                       "type": "success" if not no_tier else "warning",
                       "sticky": bool(no_tier)},
        }

    def action_unbook_legacy(self):
        count = self.royalty_line_ids._edlab_unbook_legacy()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Legacy sales"),
                       "message": _("%s legacy entr(y/ies) removed.", count),
                       "type": "success"},
        }

    def action_view_legacy_sales(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "liber_copyright_contracts_legacy.action_edlab_legacy_sale")
        action["domain"] = [
            ("product_tmpl_id", "in", self.royalty_line_ids.product_id.ids)]
        action["context"] = {"search_default_counts": 1}
        return action
