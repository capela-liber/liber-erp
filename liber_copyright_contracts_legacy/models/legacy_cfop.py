# -*- coding: utf-8 -*-
"""What a CFOP means for royalties.

The legacy base carries the CFOP of every line, and the CFOP is what tells a
sale from the paper around it: a consignment shipment (5917) moves books but
sells nothing, the settlement that follows (5113) is the sale; a donation
(5910) gives a book away and pays no author; a return (1201) takes a sale
back. The table is data, so the department fixes a code without a release."""
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

EFFECTS = [
    ("sale", "Sale (accrues royalties)"),
    ("return", "Return of a sale (deducts royalties)"),
    ("courtesy", "Courtesy / donation (no royalties)"),
    ("neutral", "No effect (shipment, transfer, sample...)"),
]

# Fallback when the row has no CFOP: the unified base still names the
# operation. Order matters -- the first pattern that matches wins.
NATURE_RULES = (
    (re.compile(r"^VENDA", re.I), "sale"),
    (re.compile(r"^DEVOLU[CÇ][AÃ]O de venda", re.I), "return"),
    (re.compile(r"^DEVOLU[CÇ][AÃ]O$", re.I), "return"),
    (re.compile(r"DOA[CÇ][AÃ]O|BRINDE|BONIFICA", re.I), "courtesy"),
)


def effect_from_nature(nature):
    """Pure fallback: classify by the operation's wording."""
    text = (nature or "").strip()
    for pattern, effect in NATURE_RULES:
        if pattern.search(text):
            return effect
    return "neutral"


class EdlabLegacyCfop(models.Model):
    _name = "edlab.legacy.cfop"
    _description = "Legacy CFOP (effect on royalties)"
    _order = "code"
    _rec_name = "code"

    code = fields.Char(required=True, size=4, index=True)
    name = fields.Char(required=True, translate=True)
    effect = fields.Selection(EFFECTS, required=True, default="neutral")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        "unique(code)", "This CFOP is already in the table.")

    @api.depends("code", "name")
    def _compute_display_name(self):
        for cfop in self:
            cfop.display_name = "%s - %s" % (cfop.code, cfop.name)

    @api.constrains("code")
    def _check_code(self):
        for cfop in self:
            if not re.fullmatch(r"\d{4}", cfop.code or ""):
                raise ValidationError(
                    _("A CFOP is exactly four digits (got %r).",
                               cfop.code))
