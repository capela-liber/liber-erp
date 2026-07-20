# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class EdlabContract(models.Model):
    _name = "edlab.contract"
    _description = "Copyright Contract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "signature_date desc, name desc"

    name = fields.Char(
        string="Number",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _("New"),
    )
    signature_date = fields.Date(string="Signature Date", tracking=True)
    expiration_date = fields.Date(string="Expiration Date", tracking=True)

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Responsible",
        tracking=True,
        default=lambda self: self.env.user,
        help="Person in charge of following this contract.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    tag_ids = fields.Many2many(
        "edlab.contract.tag",
        "edlab_contract_tag_rel",
        "contract_id",
        "tag_id",
        string="Tags",
    )

    location = fields.Char(
        string="Location",
        help="URL or filing location of the contract.",
    )
    auto_renew = fields.Boolean(string="Auto-Renewable")
    renewal_period_years = fields.Integer(
        string="Renewal Term (years)",
        default=1,
        help="Fixed term (in years) added to the expiration date on each "
        "renewal. Suggested from the initial signature-to-expiration span when "
        "the contract is created, but stays fixed afterwards so every renewal "
        "extends by the same period.",
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("valid", "Valid"),
            ("expired", "Expired"),
            ("renewed", "Renewed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )

    days_to_expiration = fields.Integer(
        string="Days to Expiration",
        compute="_compute_time_left",
        help="Days remaining until the expiration date (negative if already past).",
    )
    time_left_display = fields.Char(
        string="Time Left",
        compute="_compute_time_left",
    )

    royalty_line_ids = fields.One2many(
        "edlab.contract.royalty.line",
        "contract_id",
        string="Royalties",
        copy=True,
    )

    partner_ids = fields.Many2many(
        "res.partner",
        string="Beneficiaries",
        compute="_compute_parties",
        store=True,
    )
    product_ids = fields.Many2many(
        "product.template",
        string="Works",
        compute="_compute_parties",
        store=True,
    )

    @api.depends("royalty_line_ids.partner_id", "royalty_line_ids.product_id")
    def _compute_parties(self):
        for contract in self:
            contract.partner_ids = contract.royalty_line_ids.partner_id
            contract.product_ids = contract.royalty_line_ids.product_id

    @staticmethod
    def _term_from_dates(start, end):
        """Whole years between two dates (minimum 1), or 0 when invalid."""
        if not start or not end or end <= start:
            return 0
        delta = relativedelta(end, start)
        return (delta.years + (1 if delta.months or delta.days else 0)) or 1

    @api.onchange("signature_date", "expiration_date")
    def _onchange_suggest_renewal_term(self):
        """Suggest the renewal term from the dates while editing the form.
        It is only a suggestion: once set it stays fixed and is not recomputed
        when a renewal pushes the expiration date forward."""
        term = self._term_from_dates(self.signature_date, self.expiration_date)
        if term:
            self.renewal_period_years = term

    @api.depends("expiration_date", "state")
    def _compute_time_left(self):
        today = fields.Date.today()
        for contract in self:
            if not contract.expiration_date or contract.state in ("cancelled", "expired"):
                contract.days_to_expiration = 0
                contract.time_left_display = ""
                continue
            days = (contract.expiration_date - today).days
            contract.days_to_expiration = days
            if days < 0:
                contract.time_left_display = _("Expired")
            elif days <= 360:
                unit = _("day") if days == 1 else _("days")
                contract.time_left_display = "%s %s" % (days, unit)
            else:
                years = days // 365
                months = (days % 365) // 30
                year_part = "%s %s" % (years, _("year") if years == 1 else _("years"))
                if months:
                    month_part = "%s %s" % (
                        months,
                        _("month") if months == 1 else _("months"),
                    )
                    contract.time_left_display = "%s %s %s" % (
                        year_part,
                        _("and"),
                        month_part,
                    )
                else:
                    contract.time_left_display = year_part

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "edlab.contract",
                    sequence_date=vals.get("signature_date"),
                ) or _("New")
            if not vals.get("renewal_period_years"):
                term = self._term_from_dates(
                    fields.Date.to_date(vals.get("signature_date")),
                    fields.Date.to_date(vals.get("expiration_date")),
                )
                if term:
                    vals["renewal_period_years"] = term
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # State actions (buttons)
    # ------------------------------------------------------------------
    def action_validate(self):
        """Mark the contract(s) as Valid."""
        self.write({"state": "valid"})

    def action_cancel(self):
        """Cancel the contract(s)."""
        self.write({"state": "cancelled"})

    def action_renew(self):
        """Manual renewal: extend the expiration date and mark as Renewed."""
        for contract in self:
            contract._extend_expiration()
            contract.state = "renewed"
            contract.message_post(
                body=_("Contract renewed until %s.", contract.expiration_date)
            )

    def _extend_expiration(self, years=None):
        """Push the expiration date forward by the renewal term (in years)."""
        self.ensure_one()
        years = years or self.renewal_period_years or 1
        base = self.expiration_date or fields.Date.today()
        self.expiration_date = base + relativedelta(years=years)

    # ------------------------------------------------------------------
    # Automation (daily cron)
    # ------------------------------------------------------------------
    @api.model
    def _cron_update_contract_states(self):
        """Mark expired contracts; auto-renew the ones flagged `auto_renew`."""
        today = fields.Date.today()
        # Include already-expired contracts too: flagging an expired contract as
        # auto-renewable should let the daily job bring it back into force.
        contracts = self.search(
            [
                ("state", "in", ["valid", "renewed", "expired"]),
                ("expiration_date", "!=", False),
                ("expiration_date", "<", today),
            ]
        )
        for contract in contracts:
            if contract.auto_renew and (contract.renewal_period_years or 0) > 0:
                # capture the term once so the loop doesn't compound the period
                term = contract.renewal_period_years
                guard = 0
                while contract.expiration_date < today and guard < 120:
                    contract._extend_expiration(years=term)
                    guard += 1
                contract.state = "renewed"
                contract.message_post(
                    body=_(
                        "Automatically renewed until %s.", contract.expiration_date
                    )
                )
            else:
                contract.state = "expired"
        # Schedule "expiring soon" reminders for the responsible person
        self._schedule_expiry_reminders(today)

    @api.model
    def _schedule_expiry_reminders(self, today=None):
        """Create a To-Do activity for the responsible before expiry.

        The reminder window (in days) is a general default configured in
        Settings (system parameter copyright_contracts.expiry_reminder_days).
        """
        today = today or fields.Date.today()
        days = int(self.env["ir.config_parameter"].sudo().get_param(
            "copyright_contracts.expiry_reminder_days", 45))
        limit = today + relativedelta(days=days)
        todo = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not todo:
            return
        contracts = self.search(
            [
                ("state", "in", ["valid", "renewed"]),
                ("user_id", "!=", False),
                ("expiration_date", "!=", False),
                ("expiration_date", ">=", today),
                ("expiration_date", "<=", limit),
            ]
        )
        summary = _("Contract expiring soon")
        for contract in contracts:
            # idempotent: skip if this reminder is already pending on the contract
            already = contract.activity_ids.filtered(
                lambda a: a.activity_type_id == todo and a.summary == summary
            )
            if already:
                continue
            # Deadline = today so it shows up as an actionable (coloured) activity.
            contract.activity_schedule(
                "mail.mail_activity_data_todo",
                date_deadline=today,
                summary=summary,
                note=_(
                    "This contract expires on %s. Review renewal or cancellation.",
                    contract.expiration_date,
                ),
                user_id=contract.user_id.id,
            )
