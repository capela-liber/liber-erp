# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class EdlabContractRoyaltyLine(models.Model):
    _name = "edlab.contract.royalty.line"
    _description = "Royalty Line (beneficiary x work)"

    contract_id = fields.Many2one(
        "edlab.contract",
        string="Contract",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Beneficiary",
        required=True,
    )
    product_id = fields.Many2one(
        "product.template",
        string="Work",
        required=True,
    )
    tier_ids = fields.One2many(
        "edlab.contract.royalty.tier",
        "line_id",
        string="Tiers",
        copy=True,
    )
    company_id = fields.Many2one(
        related="contract_id.company_id",
        store=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related="contract_id.currency_id",
        string="Currency",
    )
    recoupable_advance = fields.Monetary(
        string="Recoupable Advance",
        currency_field="currency_id",
        help="Advance already paid to the beneficiary for this work, "
        "recoupable against the royalties accrued on it.",
    )
    non_recoupable_advance = fields.Monetary(
        string="Non-Recoupable Advance",
        currency_field="currency_id",
    )

    _sql_constraints = [
        (
            "partner_product_uniq",
            "unique(contract_id, partner_id, product_id)",
            "A line already exists for this beneficiary and this work in this contract.",
        ),
    ]


class EdlabContractRoyaltyTier(models.Model):
    _name = "edlab.contract.royalty.tier"
    _description = "Copies Tier"
    _order = "qty_from"

    line_id = fields.Many2one(
        "edlab.contract.royalty.line",
        string="Royalty Line",
        required=True,
        ondelete="cascade",
        index=True,
    )
    qty_from = fields.Integer(string="From (copies)", default=0)
    qty_to = fields.Integer(
        string="To (copies)",
        help="Leave 0 to indicate 'no upper limit'.",
    )
    percentage = fields.Float(string="Percentage (%)", digits=(5, 2))

    @api.constrains("qty_from", "qty_to")
    def _check_range(self):
        for tier in self:
            if tier.qty_to and tier.qty_to < tier.qty_from:
                raise ValidationError(
                    _("The end quantity must be greater than or equal to the start quantity.")
                )
