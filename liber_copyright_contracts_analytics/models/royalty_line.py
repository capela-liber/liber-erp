# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare

MANAGER_GROUP = "liber_copyright_contracts.group_contract_manager"


class EdlabContractRoyaltyLine(models.Model):
    _inherit = "edlab.contract.royalty.line"

    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        help="Analytic account tracking this work/beneficiary pair.",
    )
    analytic_name = fields.Char(
        string="Analytic Name",
        compute="_compute_analytic_name",
        help="Suggested analytic account name: contract number, product "
        "internal reference, product name and beneficiary name.",
    )
    last_payment_date = fields.Date(
        string="Last Payment Date",
        help="Date of the last royalty payment. "
        "Editable by Contracts Administrators only.",
    )
    on_sales_price = fields.Boolean(
        string="On Sales Price",
        help="Compute this line's royalties on the gross sales price (cover "
        "price, i.e. the invoice unit price before the discount) instead of the "
        "net invoiced amount.",
    )

    @api.depends(
        "contract_id.name",
        "product_id",
        "product_id.default_code",
        "partner_id.name",
        "partner_id.parent_id.name",
    )
    def _compute_analytic_name(self):
        for line in self:
            line.analytic_name = line._prepare_analytic_name()

    def _prepare_analytic_name(self):
        """Analytic name: 'Contracts: [Number] [Ref] Work Beneficiary (Company)'."""
        self.ensure_one()
        contract = self.contract_id.name or _("New")
        tokens = ["[%s]" % contract]
        product = self.product_id
        if product:
            ref = product.default_code
            tokens.append("[%s] %s" % (ref, product.name) if ref else product.name)
        if self.partner_id:
            tokens.append(self.partner_id.name or "")
            parent = self.partner_id.parent_id.name
            if parent:
                tokens.append("(%s)" % parent)
        return "Contracts: " + " ".join(token for token in tokens if token)

    def _book_royalties_from_invoices(self, invoices):
        """Book royalty analytic lines on each royalty line's analytic account.

        For every royalty line in ``self`` (that has an analytic account), the
        paid invoice lines selling its work are processed in chronological order
        while keeping a running total of copies sold. Each invoice line is booked
        with the tier percentage matching that **cumulative** quantity (e.g.
        1..100 -> 7%, above -> 8%), as a negative amount (= subtotal x percentage).

        Idempotent: an invoice line is never booked twice on the same analytic
        account (the running total still advances so tiers stay correct on
        re-runs). Returns an ``ir.actions.client`` notification.
        """
        AnalyticLine = self.env["account.analytic.line"]

        # "Nothing to do" has three very different causes, and saying "already up
        # to date" for all of them is a lie by omission: it tells the user their
        # work is done when in fact nothing could even be attempted. Name the
        # cause, and say what to fix.
        without_account = self.filtered(lambda r: not r.analytic_account_id)
        if not (self - without_account):
            return self._edlab_notify(_(
                "No royalty line has an analytic account, so there is nowhere to "
                "book. Create the analytic accounts first (%s line(s) waiting).",
                len(without_account)), success=False)

        # NOTE: no early return when `invoices` is empty. Paying a royalty bill
        # calls this method with an EMPTY recordset on purpose: there is no sale
        # to accrue, only the payment cutoff to settle. Bailing out here would
        # silently stop payments from reaching the analytic accounts. The "no
        # paid invoice" message is reported at the end instead.
        self._edlab_book_advance()
        created = 0
        no_tier = self.env["edlab.contract.royalty.line"]
        out_of_term = self.env["account.move.line"]
        in_term_seen = 0
        for royalty in self:
            account = royalty.analytic_account_id
            if not account:
                continue
            on_sales_price = royalty.on_sales_price
            company = royalty.company_id or self.env.company
            special_teams = company.contract_special_sales_team_ids
            min_discount = company.contract_special_min_discount
            contract = royalty.contract_id
            # No tier means no percentage, and booking a 0% / R$ 0,00 entry per
            # invoice line would quietly fill the analytic account with noise
            # that looks like a settled royalty. Accrue nothing -- but fall
            # through to the payment cutoff below: what the beneficiary was
            # already PAID has to settle regardless of how the accrual is set up.
            if not royalty.tier_ids:
                no_tier |= royalty
                invoice_lines = self.env["account.move.line"]
            else:
                # A contract only earns royalties on the sales made WHILE IT WAS
                # IN FORCE. A sale invoiced after the contract expired (or before
                # it was signed) is outside the term and accrues nothing -- which
                # is what makes an expired contract stop taking new entries,
                # without freezing what it legitimately earned while alive.
                invoice_lines = invoices.invoice_line_ids.filtered(
                    lambda l: l.product_id
                    and l.price_subtotal
                    and l.product_id.product_tmpl_id == royalty.product_id
                ).sorted(key=lambda l: (l.move_id.invoice_date or l.move_id.date, l.id))
                outside = invoice_lines.filtered(
                    lambda l: not contract._edlab_in_term(
                        l.move_id.invoice_date or l.move_id.date))
                out_of_term |= outside
                invoice_lines -= outside
                in_term_seen += len(invoice_lines)
            cumulative = 0.0
            for line in invoice_lines:
                cumulative += line.quantity
                if AnalyticLine.search_count(
                    [
                        ("edlab_source_move_line_id", "=", line.id),
                        ("account_id", "=", account.id),
                    ]
                ):
                    continue
                percentage = royalty._royalty_percentage_for_qty(cumulative)
                move = line.move_id
                # Special sales are always computed on the net invoiced amount,
                # never on the sales/cover price, overriding "On Sales Price".
                # A sale is special when its team is one of the configured
                # special teams and the line discount reaches the minimum.
                is_special = bool(
                    special_teams
                    and move.team_id in special_teams
                    and line.discount >= min_discount
                )
                # Base: gross sales price (unit price x qty, before discount) when
                # "On Sales Price" is on and it is not a special sale; otherwise
                # the net invoiced subtotal.
                use_net = (not on_sales_price) or is_special
                base = (
                    line.price_subtotal
                    if use_net
                    else line.price_unit * line.quantity
                )
                AnalyticLine.create(
                    {
                        "name": "%.2f%%" % percentage,
                        "account_id": account.id,
                        "date": move.invoice_date or move.date,
                        "amount": -(base * percentage / 100.0),
                        "unit_amount": line.quantity,
                        "partner_id": royalty.partner_id.id,
                        "product_id": line.product_id.id,
                        "company_id": line.company_id.id,
                        "edlab_royalty_percentage": percentage,
                        "ref": move.name,
                        "edlab_source_move_line_id": line.id,
                    }
                )
                created += 1
            # Payment cutoff: the beneficiary's last payment date settles every
            # royalty accrued up to it. Book one compensating entry on that date
            # that zeroes the balance accrued so far (as if paid by a bill).
            cutoff = royalty.last_payment_date
            if cutoff:
                debt = sum(
                    AnalyticLine.search(
                        royalty._edlab_accrual_entry_domain()
                        + [("date", "<=", cutoff)]
                    ).mapped("amount")
                )
                # The recoupable advance is money the beneficiary ALREADY has:
                # the bill deducts it from the accruals, so the settlement must
                # too, or the entry booked here differs from what was paid, the
                # account is left at +advance instead of zero, and the advance
                # gets recouped AGAIN on the next cycle. The statement relies on
                # this (the cutoff closes everything up to its date, advance
                # included) to not deduct a settled advance twice.
                debt += sum(
                    AnalyticLine.search(
                        [
                            ("edlab_advance_line_id", "=", royalty.id),
                            ("date", "<=", cutoff),
                        ]
                    ).mapped("amount")
                )
                desired = -debt
                existing = AnalyticLine.search(
                    [("edlab_payment_cutoff_line_id", "=", royalty.id)]
                )
                up_to_date = (
                    len(existing) == 1
                    and existing.date == cutoff
                    and float_compare(existing.amount, desired, precision_digits=2) == 0
                )
                if not up_to_date:
                    existing.unlink()
                    # Only a POSITIVE settlement makes sense: when the advance
                    # still exceeds everything accrued, nothing was (or could
                    # be) paid, and a negative "Payment" would silently wipe
                    # the leftover advance that future royalties must recoup.
                    if float_compare(desired, 0.0, precision_digits=2) > 0:
                        AnalyticLine.create(
                            {
                                "name": _("Payment"),
                                "account_id": account.id,
                                "date": cutoff,
                                "amount": desired,
                                "partner_id": royalty.partner_id.id,
                                "company_id": royalty.company_id.id,
                                "ref": _("Bill"),
                                "edlab_payment_cutoff_line_id": royalty.id,
                            }
                        )
                        created += 1
        skipped = ""
        if no_tier:
            skipped = _(" %s royalty line(s) have no percentage tier and were "
                        "skipped.", len(no_tier))
        if out_of_term:
            skipped += _(" %s invoice line(s) fall outside the contract term "
                         "(sold before it was signed or after it expired) and "
                         "accrue no royalty.", len(out_of_term))
        if created:
            return self._edlab_notify(
                _("%s royalty line(s) added.") % created + skipped,
                success=not no_tier)

        # Nothing accrued and nothing settled, and there was no sale to accrue
        # from in the first place.
        if not invoices:
            return self._edlab_notify(_(
                "No PAID customer invoice to book from. Royalties are only booked "
                "on invoices that are posted AND paid, so an invoice that is "
                "merely posted still counts for nothing here.") + skipped,
                success=False)

        # Still nothing? Then either the contracted works were never sold, or
        # they were and everything is already booked. Those read the same to the
        # user ("nothing happened") and mean opposite things, so separate them.
        # Every sale of the works is outside the contract term: the contract
        # expired (or was cancelled, or the sales predate its signature). Say
        # THAT -- "already booked" would claim work was done when none was.
        if out_of_term and not in_term_seen:
            return self._edlab_notify(_(
                "No new lines: all %(n)s sale(s) of the contracted work(s) fall "
                "outside the contract term, so they accrue no royalty. A "
                "contract only earns on what was sold while it was in force.",
                n=len(out_of_term)), success=False)

        sold = invoices.invoice_line_ids.product_id.product_tmpl_id
        booked = self.filtered(lambda r: r.analytic_account_id) - no_tier
        never_sold = booked.filtered(lambda r: r.product_id not in sold)
        if not booked:
            return self._edlab_notify(
                _("No new lines: no royalty line has a percentage tier, so "
                  "nothing can be computed. Set the tiers first (%s line(s) "
                  "waiting).", len(no_tier)), success=False)
        if len(never_sold) == len(booked):
            note = _("No new lines: none of the %(n)s contracted work(s) appears "
                     "in a paid invoice, so no royalty has accrued yet.",
                     n=len(booked))
        else:
            note = _("No new lines: every paid invoice selling a contracted work "
                     "is already booked (%(inv)s invoice(s) checked).",
                     inv=len(invoices))
            if never_sold:
                note += _(" %s work(s) under contract have not been sold yet.",
                          len(never_sold))
        if without_account:
            note += _(" %s royalty line(s) have no analytic account and were "
                      "skipped.", len(without_account))
        return self._edlab_notify(note + skipped, success=False)

    def _edlab_notify(self, message, success=True):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Royalty analytic lines"),
                "message": message,
                "type": "success" if success else "warning",
                "sticky": not success,
            },
        }

    def _edlab_accrual_entry_domain(self):
        """Domain of the analytic entries that ACCRUE royalties on this
        line's account (used by the payment cutoff and the statement).
        Extension hook: other modules add their own accrual kinds here
        (e.g. the NFe audit residuals)."""
        self.ensure_one()
        return [
            ("account_id", "=", self.analytic_account_id.id),
            ("edlab_source_move_line_id", "!=", False),
        ]

    def _royalty_percentage_for_qty(self, quantity):
        """Return the tier percentage matching `quantity` (own-invoice rule).

        A tier with ``qty_to = 0`` means "no upper limit". If no tier matches
        (e.g. quantity below the first tier), fall back to the last tier.
        """
        self.ensure_one()
        tiers = self.tier_ids.sorted("qty_from")
        for tier in tiers:
            below_upper = (not tier.qty_to) or quantity <= tier.qty_to
            if quantity >= tier.qty_from and below_upper:
                return tier.percentage
        return tiers[-1].percentage if tiers else 0.0

    def action_create_analytic_account(self):
        """Create the analytic account (or resync its name) for each line."""
        Analytic = self.env["account.analytic.account"]
        for line in self:
            if not (line.product_id and line.partner_id):
                raise UserError(_("Set the beneficiary and the work first."))
            name = line._prepare_analytic_name()
            if line.analytic_account_id:
                line.analytic_account_id.name = name
            else:
                company = line.company_id or self.env.company
                vals = {
                    "name": name,
                    "company_id": company.id,
                    "partner_id": line.partner_id.id,
                }
                # v19: analytic accounts require a plan_id (was optional group_id).
                # NAO usar "o primeiro plano que existir": era isso que fazia as
                # contas de royalty nascerem dentro do plano Project.
                plan = company._contract_analytic_plan()
                if not plan:
                    raise UserError(_(
                        "No analytic plan for copyright contracts: the default "
                        "plan shipped with this module is gone. Choose one under "
                        "Settings > Copyright > Royalty Accounting."))
                vals["plan_id"] = plan.id
                line.analytic_account_id = Analytic.create(vals)
        self._edlab_book_advance()
        return True

    def _edlab_book_advance(self):
        """Book (or refresh) each line's recoupable advance as a positive
        opening entry on its analytic account, dated at the contract signature.

        The advance is money already paid to the beneficiary, so it lands as a
        positive amount that the royalties accruing on the work recoup before
        anything new is owed. Idempotent: one entry per royalty line, updated
        when the advance changes and removed when it is cleared.
        """
        AnalyticLine = self.env["account.analytic.line"].sudo()
        today = fields.Date.context_today(self)
        for royalty in self:
            existing = AnalyticLine.search(
                [("edlab_advance_line_id", "=", royalty.id)]
            )
            account = royalty.analytic_account_id
            advance = royalty.recoupable_advance
            if not account or float_compare(advance, 0.0, precision_digits=2) <= 0:
                existing.unlink()
                continue
            date = royalty.contract_id.signature_date or today
            vals = {
                "name": _("Recoupable advance"),
                "account_id": account.id,
                "date": date,
                "amount": advance,
                "partner_id": royalty.partner_id.id,
                "company_id": royalty.company_id.id,
                "ref": _("Advance"),
                "edlab_advance_line_id": royalty.id,
            }
            if existing:
                existing[1:].unlink()
                existing[0].write(vals)
            else:
                AnalyticLine.create(vals)

    # ------------------------------------------------------------------
    # Last payment date: administrators only
    # ------------------------------------------------------------------
    # The guard blocks regular users from setting the date by hand; elevated
    # (sudo) writes are allowed so automatic settlements — e.g. the payments
    # module stamping the date when a royalty bill is paid — go through.
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self.env.user.has_group(MANAGER_GROUP):
            for vals in vals_list:
                if vals.get("last_payment_date"):
                    raise AccessError(
                        _("Only a Contracts Administrator can set the last payment date.")
                    )
        return super().create(vals_list)

    def write(self, vals):
        if (
            "last_payment_date" in vals
            and not self.env.su
            and not self.env.user.has_group(MANAGER_GROUP)
        ):
            raise AccessError(
                _("Only a Contracts Administrator can change the last payment date.")
            )
        res = super().write(vals)
        if {"recoupable_advance", "analytic_account_id"} & set(vals):
            self._edlab_book_advance()
        return res
